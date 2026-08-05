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

variable "enable_cdn" {
  description = <<-EOT
    Put S3 + CloudFront in front of the function, so static files are served from the edge
    and one hostname covers both the page and the API.

    Off in dev by default, and the reason is teardown time, not money: an idle
    distribution costs nothing, but destroying one takes about 15 minutes against 22
    seconds without it, and this repository is built on destroying environments often.
    Turn it on in dev when the CDN path itself is what you are testing.
  EOT
  type        = bool
  default     = false
}

variable "cdn_price_class" {
  description = "PriceClass_100 is North America and Europe only, and the cheapest."
  type        = string
  default     = "PriceClass_100"
}
