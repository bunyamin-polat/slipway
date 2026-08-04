# Slipway · AWS Deployment Blueprint

> **GitHub repo description:** Terraform + GitHub Actions blueprint for shipping containerised AI apps to AWS — Lambda with response streaming, S3, CloudFront, multi-environment workspaces, one-command deploy.

> **A blueprint to copy from, not a service to depend on.** Every other repo in this portfolio says "Dockerfile" and stops. This is the one that puts a container on the internet, with infrastructure as code and a deploy pipeline. Build it first; every later project starts by copying the modules it needs out of here.

> **Standalone and self-contained.** This repo depends on nothing else, and **nothing depends on it at run time**. It ships its own minimal example app in `template/app/`, so `git clone && python scripts/deploy.py dev` produces a live URL for someone who has never seen the rest of the portfolio. Written from scratch, and useful to a stranger — that is what separates a blueprint from a deploy script that happens to live in a repo.

## 1. What it is

A reusable deployment blueprint: Terraform modules, deployment scripts and GitHub Actions workflows that take a containerised FastAPI + static-frontend application from a local repo to a running AWS environment — with separate dev, test and prod environments, secrets managed properly, and a rollback path.

The AI content is deliberately near zero. That is the point. A portfolio full of LLM demos with no deployment story reads as a hobbyist; the same portfolio where every app has a live URL, a Terraform state and a green deploy badge reads as an engineer. This repo is what makes the difference, once, for all of them.

## 2. Origin

Written from scratch, informed by two patterns worth stating up front.

**Modules versus stacks.** A single Terraform configuration with workspaces is exactly right at small scale. It stops being right once one state file holds a database, eight functions and a CDN distribution — at that size `apply` becomes frightening and people stop running it. The split here is: reusable modules with no state, composed by numbered stacks that each own their own state. Start with one `20_app` stack and split when it hurts.

**Scripts, not raw Terraform.** `terraform apply` is never the whole story — there is also build, push to a registry, and CDN invalidation, and that sequence has to be one command or it will eventually be done wrong at 11pm. Hence `scripts/`, and hence `destroy.py` being a first-class citizen rather than an afterthought.

## 3. Core capabilities

- **Multi-stage container build** — frontend static export built in one stage, copied into a slim Python runtime in the next. One image, one artifact.
- **Lambda with response streaming** — the Lambda Web Adapter lets a normal FastAPI app run unchanged on Lambda, and `response_stream` invoke mode keeps SSE working, which every streaming LLM UI needs.
- **Two compute targets behind one interface** — Lambda (scale to zero, pay per request, cold starts) and App Runner / ECS Fargate (always warm, fixed cost). Pick per project, not per portfolio.
- **Static frontend delivery** — S3 + CloudFront with cache invalidation on deploy.
- **Terraform workspaces** — one configuration, isolated state for `dev`, `test`, `prod`, with per-environment `.tfvars`.
- **Secrets handled properly** — AWS Secrets Manager / SSM Parameter Store, never `.tfvars` in git, never baked into the image.
- **One-command deploy and destroy** — `./deploy.sh test`, `./destroy.sh test`. The destroy path matters more than the deploy path: it is what stops a forgotten environment quietly billing you.
- **GitHub Actions pipeline** — build, test, push to ECR, `terraform plan` on PR, `terraform apply` on merge, with a manual approval gate for prod.
- **Cost guardrails from minute one** — AWS Budgets with alerts before any resource exists.
- **Cookiecutter-style project template** so a new app adopts the whole thing in one command.

## 4. Proposed product structure

```text
slipway/
├── terraform/
│   ├── modules/
│   │   ├── lambda_container/     # ECR image → Lambda + LWA + streaming, IAM, log group
│   │   ├── apprunner_service/    # Always-on alternative to lambda_container
│   │   ├── static_site/          # S3 bucket + CloudFront + OAC + invalidation
│   │   ├── http_api/             # API Gateway HTTP API, routes, throttling, CORS
│   │   ├── data_bucket/          # Application S3 storage, lifecycle rules, encryption
│   │   ├── secrets/              # Secrets Manager / SSM parameters + IAM policy
│   │   ├── observability/        # CloudWatch dashboards, alarms, log retention
│   │   └── budget/               # AWS Budgets + SNS alerts — apply this first
│   ├── stacks/
│   │   ├── 00_bootstrap/         # Budget alarm, remote state bucket, ECR repository
│   │   ├── 10_network/           # Only if you need a VPC — most apps do not
│   │   └── 20_app/               # Composes the modules into a deployable app
│   ├── envs/
│   │   ├── dev.tfvars
│   │   ├── test.tfvars
│   │   └── prod.tfvars
│   └── README.md                 # Which stack does what, and in which order
├── docker/
│   ├── Dockerfile.fastapi        # Python-only backend
│   ├── Dockerfile.fullstack      # Multi-stage: Next.js export → Python runtime + LWA
│   └── .dockerignore
├── scripts/
│   ├── deploy.py                 # Build → push to ECR → terraform apply → invalidate CDN
│   ├── destroy.py                # Tear down an environment completely, with confirmation
│   ├── run_local.py              # Same container, locally, with the same env contract
│   ├── bootstrap.py              # One-time: remote state, ECR repo, OIDC role, budget
│   └── smoke.py                  # Post-deploy health checks; non-zero exit fails the pipeline
├── .github/workflows/
│   ├── ci.yml                    # Lint, test, build image on every PR
│   ├── plan.yml                  # terraform plan, posted as a PR comment
│   ├── deploy-dev.yml            # Auto-deploy on merge to main
│   └── promote.yml               # Manual approval → test → prod
├── template/                     # Cookiecutter project skeleton
│   ├── app/                      # Minimal FastAPI + static frontend that deploys as-is
│   ├── Dockerfile
│   └── slipway.yaml              # Per-app config: name, compute target, env vars, secrets
├── docs/
│   ├── first-deploy.md           # Zero to a live URL
│   ├── cost.md                   # What each resource costs, and how to keep it near zero
│   ├── secrets.md
│   └── rollback.md
├── tests/
│   ├── test_terraform_fmt.py     # fmt, validate, tflint across all modules
│   └── test_scripts.py
├── .env.example
└── README.md
```

**No UI.** This is a CLI and a set of workflows. The "interface" is `python scripts/deploy.py test` and a green check on a pull request. Resist the urge to build a dashboard for it — the GitHub Actions run page and the CloudWatch dashboard already exist.

**Why this shape:** `terraform/modules/` versus `terraform/stacks/` is the important split. Modules are reusable pieces with no state; stacks are the things you actually apply, each with its own state file. A single monolithic configuration with workspaces is exactly right at small scale; splitting into numbered stacks becomes necessary once one state file holds a database, eight functions and a CDN distribution, because at that size `apply` becomes frightening and people stop running it. Start with one `20_app` stack and split when it hurts. `scripts/` exists because raw `terraform apply` is never the whole story — you also have to build, push, and invalidate the CDN, and that sequence must be one command or it will be done wrong at 11pm.

## 5. Models used

None. This repo deploys applications that use models; it does not call any itself.

The one model-adjacent decision it does encode: **which region**, because Bedrock model availability varies by region and you do not want your app in `eu-west-1` and your models in `us-west-2` unless you meant it.

## 6. Libraries & services

**IaC:** Terraform ≥ 1.11 (workspaces, remote state in S3 with native locking via `use_lockfile`, `tflint`, `terraform fmt`)
**AWS:** Lambda (container images), [AWS Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter), ECR, S3, CloudFront, API Gateway HTTP API, IAM, Secrets Manager / SSM Parameter Store, CloudWatch, AWS Budgets, EventBridge; App Runner or ECS Fargate as the always-on option
**Containers:** Docker, multi-stage builds, `docker buildx` for `linux/amd64` from an ARM Mac — **this catches everyone once**
**CI/CD:** GitHub Actions, OIDC federation to AWS (no long-lived access keys in secrets)
**Scripting:** Python + `boto3`, `uv`
**Local:** Docker Desktop, AWS CLI v2
**Optional:** `checkov` or `tfsec` for IaC security scanning — cheap to add, good signal

## 7. Productization notes

- **Set the budget alarm before the first `terraform apply`.** A NAT Gateway you forgot about is roughly $32 a month, forever, for nothing.
- **`destroy` is a first-class feature.** Write it, test it, and use it. Every environment you cannot confidently destroy is a subscription you did not intend to buy.
- **Remote state from the start.** Local `terraform.tfstate` works until you deploy from CI, or from a second machine, or lose the file — after which recovery is manual and miserable. `00_bootstrap` exists for exactly this, and it is the one stack that starts with local state, because it is the thing that creates the bucket. Move it with `terraform init -migrate-state` once the bucket exists.
- **OIDC, not access keys.** GitHub Actions can assume an AWS role directly. Long-lived `AWS_SECRET_ACCESS_KEY` in repo secrets is the most common way portfolio projects leak credentials.
- **Build for `linux/amd64` explicitly.** An image built on Apple Silicon fails on Lambda with an opaque error. `--platform linux/amd64` in the build script, not in a comment.
- **Streaming needs the invoke mode set.** The Lambda Web Adapter defaults to buffered responses; SSE silently stops working. `AWS_LWA_INVOKE_MODE=response_stream` plus a Lambda Function URL — miss this and every streaming UI in your portfolio delivers its answer in one lump at the end.
- **Lambda cold starts are real for container images.** A few hundred MB of Python plus model client libraries is seconds of cold start. Provisioned concurrency costs money; App Runner is often the better answer for anything user-facing and interactive. Encode the choice per app, and say why in each app's README.
- **Adopters vendor, they do not reference.** Terraform can pull a module straight from a git URL. Do not document that as the way to use this repo. A remote `source = "git::https://github.com/…"` means every project's `apply` depends on this repo's `main` branch, and one bad commit here breaks six deployments at once. Copying costs a manual update when a module improves; referencing costs a shared failure mode. Take the copy.
- **Never commit `.tfvars` with real values.** `*.tfvars` in `.gitignore`, `*.tfvars.example` committed.
- **Tag every resource** with project and environment. It is the only way to read a bill and know which experiment is costing you.
- **One environment is enough at first.** Three workspaces is the pattern; you personally may only ever run `dev` plus `prod`. Build the capability, use what you need.

## 8. Build order

1. **Bootstrap.** A budget alarm with an email alert first, then the remote state bucket and the ECR repository. `terraform apply` on nothing but plumbing. State locking is the S3 backend's own (`use_lockfile`), not a DynamoDB table — that mechanism was deprecated in Terraform 1.11 and the table is one more resource to pay for and forget about.
2. **Write the example app, in this repo.** `template/app/` — a FastAPI service with one streaming endpoint and a static page, forty lines, no AI. Containerise it with `Dockerfile.fastapi` and run it through `run_local.py`. Its frontend is a single static page, so there is nothing for a Node build stage to do; `Dockerfile.fullstack` is for adopters whose frontend has a real build step, and it gets proven when one of them uses it rather than by a fake example here. Deliberately trivial: the payload must never be the interesting part, and the blueprint must be provable without any other repository existing.
3. **Deploy it manually, once, by hand.** Push to ECR, create the Lambda in the console, wire a Function URL. You will never understand the Terraform until you have done this once with your own fingers.
4. **Terraform the same thing.** `20_app` stack composing `lambda_container` + `data_bucket` + `secrets` + `budget`. Destroy the manual one first. `deploy.py` does build → push → apply.
5. **Add the frontend path.** `static_site` module: S3 + CloudFront + OAC, invalidation on deploy.
6. **Streaming and smoke tests.** Response-stream invoke mode, verify SSE end to end from the deployed URL, `smoke.py` as the gate.
7. **Workspaces.** `dev` and `prod`, per-env tfvars, and a `destroy.py` you have actually run.
8. **GitHub Actions.** OIDC role, CI on PR, `terraform plan` as a PR comment, auto-deploy to dev on merge, manual approval to prod.
9. **Observability + the alternative compute target.** CloudWatch dashboard and alarms; `apprunner_service` module for apps that should stay warm.
10. **Template it.** `template/` plus `slipway.yaml`, so adopting this in a new repo is one command. Then adopt it in a second project to prove the abstraction holds.

## 9. Putting it on GitHub

- **This is the repo that says "I can ship."** Most AI portfolios stop at a screenshot of localhost. Lead the README with the architecture diagram and the one-line deploy command.
- **The hero artifact is a live URL plus its Terraform.** Link a deployed app, then link the exact stack that created it.
- **Publish the cost breakdown.** "This runs at roughly $X/month at low traffic, and $0 when idle on Lambda" is concrete, useful, and shows you have looked at a bill.
- **Show the PR flow**: `terraform plan` posted as a comment, then an approval gate before prod. One screenshot communicates the whole practice.
- **Document the three things that bite everyone** — `linux/amd64`, response-stream invoke mode, and forgetting to destroy. A troubleshooting section built from real scars is the most-read part of any infra README.
- **Make it genuinely reusable.** If someone can clone it, fill in `slipway.yaml`, and deploy their own FastAPI app, this stops being a personal script and starts being a tool. That is the difference between a repo people skim and one they star.

---

**Related:** nothing, by design. This repo is built first and alone, and no other repository imports it, calls it, or references its Terraform remotely. Projects that use it — [Groundwork](https://github.com/bunyamin-polat/groundwork), [Assay](https://github.com/bunyamin-polat/assay), [Winnow](https://github.com/bunyamin-polat/winnow), [Triage](https://github.com/bunyamin-polat/triage), [Vitals](https://github.com/bunyamin-polat/vitals), [Chart](https://github.com/bunyamin-polat/chart) — do so by **copying** modules into their own `infra/` at setup time and owning them from then on.
