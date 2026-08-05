# Terraform layout

Two directories, one distinction that matters.

**`modules/`** — reusable pieces with no state of their own. They take variables and
create resources. Nothing here is applied directly.

**`stacks/`** — the things you actually apply. Each owns its own state file and composes
modules into something deployable. Numbered by the order they are applied in.

Environment-specific values for `20_app` come from **`slipway.yaml`** at the repository
root: `deploy.py` resolves it for the environment and passes the values as `-var` flags.
There are no `*.tfvars` for the app stack — one file, one place for a value to be wrong.

`00_bootstrap` is the exception. It runs once per account, by hand, before any script
exists, so it keeps a gitignored `terraform.tfvars` of its own.

## Stacks, in order

| Stack | Applied | State | What it owns |
| --- | --- | --- | --- |
| `00_bootstrap` | Once per account | Local, then migrated to S3 | Budget alarm, remote state bucket, ECR repository |
| `10_network` | Only if you need a VPC | S3 | VPC, subnets, NAT — most apps do not need this, and a NAT gateway costs about $32/month |
| `20_app` | Per environment | S3, one workspace per environment | Lambda + Function URL today; static site, data bucket and secrets as they are needed |

## Modules

| Module | Status | What it does |
| --- | --- | --- |
| `budget` | ✅ built | Monthly cost budget with email alerts. Apply before anything else. |
| `lambda_container` | ✅ built | ECR image → Lambda with the Web Adapter and response streaming, Function URL, scoped IAM, log group with retention |
| `static_site` | ✅ built | Private S3 + CloudFront + OAC, optional second origin for the API, invalidation on deploy |
| `data_bucket` | planned | Application storage, lifecycle rules, encryption |
| `secrets` | planned | Secrets Manager / SSM parameters plus the IAM policy to read them |
| `http_api` | planned | API Gateway HTTP API, routes, throttling, CORS |
| `observability` | ✅ built | Three alarms, one dashboard, cold starts charted from the logs, optional CloudFront panel |
| `apprunner_service` | ✅ built | Always-warm alternative to `lambda_container`, same image, capped autoscaling |

## Conventions

- `terraform fmt -recursive` and `terraform validate` pass before every commit; `tflint`
  runs in CI.
- Provider `default_tags` carries `Project`, `Environment` and `ManagedBy` so every
  taggable resource is tagged without repeating it.
- Modules pin `>= 5.60, < 7.0` on the AWS provider and `>= 1.11` on Terraform.
- `.terraform.lock.hcl` is committed; `.terraform/`, state files and plans are not.
- State locking is the S3 backend's own (`use_lockfile = true`). There is no DynamoDB lock
  table: Terraform 1.10 made S3 lock natively and 1.11 deprecated the DynamoDB mechanism,
  so the table is now a resource to pay for, permission and forget to delete.

## Copying these modules into another project

Copy them. Do not reference them.

```bash
cp -r slipway/terraform/modules/lambda_container my-app/infra/modules/
```

Terraform can load a module straight from a git URL, and it is tempting. It also means
every project's `apply` depends on this repository's `main` branch, so one bad commit
here breaks six deployments at once. Copying costs a manual update when a module
improves. Take that trade.
