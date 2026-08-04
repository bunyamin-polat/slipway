terraform {
  # 1.11 is the floor because state locking here is the S3 backend's own
  # (`use_lockfile`), which replaced the deprecated DynamoDB lock table.
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.60, < 7.0"
    }
  }

  # State is local until the bucket below exists — this is the stack that creates it.
  # After the apply that creates aws_s3_bucket.state, uncomment this block and run:
  #
  #   cp backend.hcl.example backend.hcl   # fill in from `terraform output`
  #   terraform init -backend-config=backend.hcl -migrate-state
  #
  # The settings live in backend.hcl rather than here because the bucket name contains
  # the account ID, and that does not belong in the repository.
  #
  # backend "s3" {}
}

provider "aws" {
  region = var.region

  # Every resource that supports tagging gets these, without repeating them per
  # resource. It is the only way to read a bill and know which project spent what.
  default_tags {
    tags = {
      Project     = var.project
      Environment = "shared"
      ManagedBy   = "terraform"
      Stack       = "00_bootstrap"
    }
  }
}
