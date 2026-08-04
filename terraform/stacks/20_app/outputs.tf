output "environment" {
  description = "Workspace this was applied to. Check it before believing anything else here."
  value       = local.environment
}

output "function_url" {
  description = "The live URL. This is the whole point of the repository."
  value       = module.app.function_url
}

output "function_name" {
  description = "Lambda function name."
  value       = module.app.function_name
}

output "log_group_name" {
  description = "Log group; `aws logs tail <this> --follow` while testing a deploy."
  value       = module.app.log_group_name
}

output "image_uri" {
  description = "Exactly which image is deployed. Traceable to a commit."
  value       = "${data.aws_ecr_repository.app.repository_url}:${var.image_tag}"
}
