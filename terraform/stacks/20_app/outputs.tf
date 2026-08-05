output "environment" {
  description = "Workspace this was applied to. Check it before believing anything else here."
  value       = local.environment
}

output "url" {
  description = <<-EOT
    The live URL — the whole point of the repository. CloudFront's domain when the CDN is
    enabled, the Function URL directly when it is not. Scripts and smoke tests read this
    one, so they do not care which shape the environment has.
  EOT
  value       = var.enable_cdn ? module.site[0].url : module.app.function_url
}

output "function_url" {
  description = "The Function URL itself, still reachable directly even behind CloudFront."
  value       = module.app.function_url
}

output "cdn_enabled" {
  description = "Whether this environment has CloudFront in front of it."
  value       = var.enable_cdn
}

output "static_bucket" {
  description = "Bucket the deploy script syncs static files into, or null without a CDN."
  value       = var.enable_cdn ? module.site[0].bucket_name : null
}

output "distribution_id" {
  description = "Distribution to invalidate after a deploy, or null without a CDN."
  value       = var.enable_cdn ? module.site[0].distribution_id : null
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
