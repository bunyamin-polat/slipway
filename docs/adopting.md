# Adopting Slipway in another repository

The claim this repository makes is that a second application can reach a live URL by
filling in one file. This is that file, and this is the path.

**Copy, do not reference.** Terraform can load a module straight from a git URL and it is
tempting. It also means every project's `apply` depends on this repository's `main`
branch, so one bad commit here breaks six deployments at once. Copying costs a manual
update when a module improves. Take that trade.

## What you copy

```bash
# from the root of your application's repository
mkdir -p infra scripts docker

cp -r /path/to/slipway/terraform/modules   infra/modules
cp -r /path/to/slipway/terraform/stacks    infra/stacks
cp    /path/to/slipway/scripts/*.py        scripts/
cp    /path/to/slipway/docker/Dockerfile.* docker/
cp    /path/to/slipway/template/slipway.yaml .
cp -r /path/to/slipway/.github/workflows   .github/workflows
```

Then edit `slipway.yaml`, and nothing else. It is the only file with your application's
name in it.

## The one file

```yaml
name: my-app
region: us-east-1

image:
  repository: my-app # the ECR repository 00_bootstrap creates
  dockerfile: docker/Dockerfile.fastapi
  context: app # where your Dockerfile's build context lives
  static_dir: app/static

compute:
  target: lambda # or apprunner
  memory: 1024
  timeout: 30

environments:
  dev:
    cdn: false
    observability: true
    log_retention_days: 7
```

There are no `*.tfvars`. The scripts read this file and generate Terraform's variables, so
a value exists in exactly one place.

## What your application has to provide

Two things, and they are the same two the Lambda Web Adapter needs:

1. **An HTTP server on `$PORT`** (8080 by default). Any framework. No Lambda-specific
   code — the adapter in the image translates invocations into ordinary HTTP.
2. **A health endpoint** — `/healthz` returning 200. App Runner polls it to decide
   readiness, and `smoke.py` gates the pipeline on it.

If your app streams, it needs nothing extra in the code. The three settings that make
streaming survive are already in the modules.

## First deploy

```bash
# 1. Account plumbing, once per AWS account. Budget alarm first, before anything billable.
cd infra/stacks/00_bootstrap
cp terraform.tfvars.example terraform.tfvars   # your email, your GitHub repo
terraform init && terraform apply

# 2. Point the app stack at the state bucket that just appeared
cd ../20_app
cp backend.hcl.example backend.hcl             # bucket = the output above
terraform init -backend-config=backend.hcl

# 3. Deploy
cd ../../..
uv run python scripts/deploy.py dev
uv run python scripts/smoke.py dev
```

And, the part that matters more:

```bash
uv run python scripts/destroy.py dev
```

Run it the same day. An environment you cannot confidently destroy is a subscription you
did not intend to buy.

## Continuous deployment

`00_bootstrap` also creates the GitHub OIDC role. Take its ARN and the state bucket name:

```bash
terraform -chdir=infra/stacks/00_bootstrap output github_actions_role_arn
terraform -chdir=infra/stacks/00_bootstrap output state_bucket_name
```

Set them as repository secrets — `gh secret set` rather than copy-paste, because
`terraform output` quotes its values and `terraform output -raw` does not:

```bash
gh secret set AWS_ROLE_ARN --body "$(terraform -chdir=infra/stacks/00_bootstrap output -raw github_actions_role_arn)"
gh secret set TF_STATE_BUCKET --body "$(terraform -chdir=infra/stacks/00_bootstrap output -raw state_bucket_name)"
```

Then add a required reviewer to the `prod` environment in *Settings → Environments*. The
approval gate lives there, not in the workflow file — without it `promote.yml` runs
straight through to production.

No `AWS_SECRET_ACCESS_KEY`. Ever. That is the point of the OIDC role.

## Things that will bite you

Each of these has already bitten this repository, and the fix is in the code:

- **`--platform linux/amd64`.** An image built on Apple Silicon dies on Lambda with
  `Runtime.InvalidEntrypoint`, which mentions nothing about architecture.
- **`--provenance=false --sbom=false`.** Docker 28 attaches attestations by default,
  which makes the push a manifest index, and Lambda refuses it with a message about
  media types.
- **Streaming needs three settings aligned**: `AWS_LWA_INVOKE_MODE=response_stream` in the
  image, `invoke_mode = "RESPONSE_STREAM"` on the Function URL, and `compress = false` on
  the CloudFront behaviour. Miss any one and the response still arrives, still looks
  correct, and is not streamed. `smoke.py` measures arrival times for exactly this reason.
- **Deleting a Lambda by hand leaves its log group and IAM role behind.** Terraform-managed
  environments do not do this. Console deploys leave debris only an inventory finds.
- **The GitHub OIDC subject claim now carries numeric IDs**
  (`repo:owner@123/repo@456:environment:dev`). The trust policy in `oidc.tf` matches both
  spellings. If you write your own, read the real claim out of CloudTrail rather than
  guessing.
