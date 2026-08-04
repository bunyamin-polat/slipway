# `20_app`

The deployable application: a container image on Lambda with a Function URL and response
streaming. One configuration, one workspace per environment.

Applied by `scripts/deploy.py`, not by hand. The commands below are what that script runs,
written out for when you need to debug it.

## First time in a new clone

```bash
cd terraform/stacks/20_app
cp backend.hcl.example backend.hcl        # bucket name from 00_bootstrap's output
terraform init -backend-config=backend.hcl
terraform workspace new dev               # or: terraform workspace select dev

cp ../../envs/dev.tfvars.example ../../envs/dev.tfvars
```

## Deploying

```bash
uv run python scripts/deploy.py dev
```

Which is: build the image for `linux/amd64` without attestations → push it to ECR tagged
with the git SHA → `terraform apply` with that tag → print the URL.

By hand, the same thing:

```bash
terraform workspace select dev
terraform apply -var-file=../../envs/dev.tfvars -var="image_tag=$(git rev-parse --short HEAD)"
```

## Destroying

```bash
uv run python scripts/destroy.py dev
```

Every environment you cannot confidently destroy is a subscription you did not intend to
buy. Run it, check the console is clean, then deploy again — if destroy does not work, the
step is not finished.

## Workspaces

`default` is refused: a `postcondition` on the caller-identity data source fails with a
message telling you to select one. Without that guard an absent-minded apply creates
`slipway-default-app` and files it in the wrong state.

State is stored per workspace under `env:/<workspace>/20_app/terraform.tfstate`, so dev
and prod cannot collide.

## Rollback

The image tag is a git SHA, so rolling back is applying an older one:

```bash
terraform apply -var-file=../../envs/dev.tfvars -var="image_tag=<older-sha>"
```

No rebuild — the image is still in ECR, subject to the lifecycle policy that keeps the
last ten.

## What this stack does not create

- **A budget.** There is one already, account-wide, from `00_bootstrap`. A second one per
  environment would count the same spend twice.
- **A data bucket or secrets.** The example app stores nothing and reads no secrets. Those
  modules get written when something actually needs them; an unused bucket is real cost
  and a real cleanup debt in exchange for proving nothing.
