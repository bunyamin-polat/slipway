# GitHub Actions → AWS without a single long-lived credential.
#
# GitHub mints a short-lived OIDC token for each workflow run; AWS trusts the issuer and
# exchanges it for temporary credentials. Nothing durable is stored in the repository, so
# there is nothing in it to leak. AWS_SECRET_ACCESS_KEY in repo secrets is the most common
# way portfolio projects lose their account, and this is the reason it never appears here.

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = var.github_oidc_thumbprints
}

data "aws_iam_policy_document" "github_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    # Without this the role would trust every GitHub repository in existence.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # And this pins it to one repository, and to specific triggers within it: the default
    # branch, pull requests, and named environments. A workflow on a fork's branch does
    # not match, which is what stops a drive-by pull request from assuming the role.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository}:ref:refs/heads/main",
        "repo:${var.github_repository}:pull_request",
        "repo:${var.github_repository}:environment:*",
      ]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project}-github-actions"
  description        = "Assumed by GitHub Actions via OIDC to plan, deploy and destroy ${var.project}"
  assume_role_policy = data.aws_iam_policy_document.github_assume_role.json

  # A workflow run is minutes, not hours. Shorter than the default hour, long enough for a
  # CloudFront apply.
  max_session_duration = 3600
}

# Scoped by hand rather than reaching for PowerUserAccess. It is more work, and it is the
# difference between a leaked token being an inconvenience and being an incident.
data "aws_iam_policy_document" "github_actions" {
  # Terraform state.
  statement {
    sid    = "TerraformState"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]

    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]
  }

  # The registry. GetAuthorizationToken cannot be scoped to a repository — it is the call
  # that hands out the login token, and AWS defines it account-wide.
  statement {
    sid       = "EcrLogin"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "EcrPushPull"
    effect = "Allow"

    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]

    resources = [aws_ecr_repository.app.arn]
  }

  statement {
    sid    = "Lambda"
    effect = "Allow"

    actions = [
      "lambda:AddPermission",
      "lambda:CreateFunction",
      "lambda:CreateFunctionUrlConfig",
      "lambda:DeleteFunction",
      "lambda:DeleteFunctionUrlConfig",
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
      "lambda:GetFunctionUrlConfig",
      "lambda:GetPolicy",
      "lambda:ListVersionsByFunction",
      "lambda:RemovePermission",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
      "lambda:UpdateFunctionUrlConfig",
    ]

    resources = ["arn:aws:lambda:*:${data.aws_caller_identity.current.account_id}:function:${var.project}-*"]
  }

  statement {
    sid    = "Logs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:DescribeLogGroups",
      "logs:ListTagsForResource",
      "logs:PutRetentionPolicy",
      "logs:TagResource",
      "logs:UntagResource",
    ]

    resources = ["arn:aws:logs:*:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project}-*"]
  }

  # Roles the deploy creates for the functions. Narrowed by name prefix so this role
  # cannot mint itself a more powerful one.
  statement {
    sid    = "IamForLambdaRoles"
    effect = "Allow"

    actions = [
      "iam:AttachRolePolicy",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:DeleteRolePolicy",
      "iam:DetachRolePolicy",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:ListRolePolicies",
      "iam:PassRole",
      "iam:PutRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
    ]

    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${var.project}-*"]
  }

  # Static site buckets, by name prefix.
  statement {
    sid    = "StaticSiteBuckets"
    effect = "Allow"

    actions = ["s3:*"]

    resources = [
      "arn:aws:s3:::${var.project}-*-static-*",
      "arn:aws:s3:::${var.project}-*-static-*/*",
    ]
  }

  # CloudFront's create and list calls are not resource-scopable — there is no ARN yet at
  # creation time, and the distribution list is account-wide by design.
  statement {
    sid    = "CloudFront"
    effect = "Allow"

    actions = [
      "cloudfront:CreateDistribution",
      "cloudfront:CreateInvalidation",
      "cloudfront:CreateOriginAccessControl",
      "cloudfront:DeleteDistribution",
      "cloudfront:DeleteOriginAccessControl",
      "cloudfront:GetCachePolicy",
      "cloudfront:GetDistribution",
      "cloudfront:GetInvalidation",
      "cloudfront:GetOriginAccessControl",
      "cloudfront:GetOriginRequestPolicy",
      "cloudfront:ListCachePolicies",
      "cloudfront:ListDistributions",
      "cloudfront:ListOriginRequestPolicies",
      "cloudfront:ListTagsForResource",
      "cloudfront:TagResource",
      "cloudfront:UntagResource",
      "cloudfront:UpdateDistribution",
    ]

    resources = ["*"]
  }

  # Read-only calls Terraform makes on every plan.
  statement {
    sid    = "ReadOnlyLookups"
    effect = "Allow"

    actions = [
      "sts:GetCallerIdentity",
      "ecr:GetRepositoryPolicy",
      "iam:GetOpenIDConnectProvider",
    ]

    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_actions" {
  name   = "deploy"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions.json
}
