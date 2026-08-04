# 20_app — the deployable application, one workspace per environment.
#
# `terraform workspace select dev` and `... prod` keep two isolated state files under one
# configuration. Everything that differs between them arrives through envs/<name>.tfvars;
# nothing in this file knows which environment it is beyond terraform.workspace.

locals {
  environment = terraform.workspace
  name_prefix = "${var.project}-${local.environment}"
}

# The workspace is load-bearing here: it names resources and separates state. Applying
# from `default` would create resources called "slipway-default-app" and quietly put
# them in the wrong state file, which is the kind of mistake that is discovered later.
data "aws_caller_identity" "current" {
  lifecycle {
    postcondition {
      condition     = terraform.workspace != "default"
      error_message = "Select a workspace first: terraform workspace select dev (or prod). The default workspace is not used in this stack."
    }
  }
}

# Created once by 00_bootstrap and shared by every environment; environments are told
# apart by image tag, not by having a registry each.
data "aws_ecr_repository" "app" {
  name = var.ecr_repository_name
}

module "app" {
  source = "../../modules/lambda_container"

  function_name = "${local.name_prefix}-app"
  image_uri     = "${data.aws_ecr_repository.app.repository_url}:${var.image_tag}"

  architecture = "x86_64"
  memory_size  = var.memory_size
  timeout      = var.timeout

  log_retention_days = var.log_retention_days

  create_function_url = true
  invoke_mode         = "RESPONSE_STREAM"

  # No CORS block: FastAPI serves both the page and the API, so there is only one origin.
}
