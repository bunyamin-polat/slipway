variable "project" {
  description = "Project name. Prefixes resource names and tags every resource."
  type        = string
  default     = "slipway"
}

variable "region" {
  description = <<-EOT
    AWS region for this stack. Pick once and keep it: Bedrock model availability varies
    by region, and you do not want the app in one region and the models in another.
  EOT
  type        = string
}

variable "budget_limit_usd" {
  description = "Monthly budget limit in USD, as a string."
  type        = string
  default     = "10"
}

variable "budget_alert_emails" {
  description = "Who gets the budget alerts."
  type        = list(string)
}

variable "state_bucket_name" {
  description = <<-EOT
    Name of the remote state bucket. Leave null to get "<project>-tfstate-<account-id>",
    which is unique without you having to invent anything. S3 bucket names are global
    across all AWS accounts, so a plain "slipway-tfstate" is almost certainly taken.
  EOT
  type        = string
  default     = null
}

variable "state_noncurrent_version_days" {
  description = "How long superseded state versions are kept before expiry."
  type        = number
  default     = 90
}

variable "ecr_repository_name" {
  description = "Name of the container repository. Leave null to get \"<project>-app\"."
  type        = string
  default     = null
}

variable "ecr_untagged_expire_days" {
  description = "Untagged images (leftovers from failed or superseded builds) expire after this many days."
  type        = number
  default     = 7
}

variable "ecr_max_image_count" {
  description = "How many images to keep in total. Older ones expire; you need a couple for rollback, not fifty."
  type        = number
  default     = 10
}

variable "ecr_force_delete" {
  description = <<-EOT
    Allow `terraform destroy` to delete the repository while it still contains images.
    Without it destroy fails, the repository survives, and it keeps billing for storage
    that nobody remembers exists.
  EOT
  type        = bool
  default     = true
}
