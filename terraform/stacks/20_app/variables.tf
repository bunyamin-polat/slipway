variable "project" {
  description = "Project name. Prefixes every resource name and tags everything."
  type        = string
  default     = "slipway"
}

variable "region" {
  description = "AWS region. Must match where the ECR repository lives."
  type        = string
}

variable "ecr_repository_name" {
  description = "Repository created by 00_bootstrap. Looked up, not created here."
  type        = string
  default     = "slipway-app"
}

variable "image_tag" {
  description = <<-EOT
    Tag of the image to deploy. `deploy.py` passes the git commit SHA, so the deployed
    version is always traceable to a commit and a rollback is a re-apply with an older
    tag.

    Defaults to "latest" only so that `terraform destroy` works without knowing what is
    currently deployed. Never rely on it for a deploy.
  EOT
  type        = string
  default     = "latest"
}

variable "memory_size" {
  description = "Lambda memory in MB. CPU scales with it, so it is really a speed dial."
  type        = number
  default     = 1024
}

variable "timeout" {
  description = "Lambda timeout in seconds. Also the ceiling on a single streamed response."
  type        = number
  default     = 30
}

variable "log_retention_days" {
  description = "CloudWatch retention. Short in dev, longer in prod."
  type        = number
  default     = 14
}
