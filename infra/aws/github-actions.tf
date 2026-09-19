data "aws_iam_policy_document" "github_actions_assume" {
  count = var.github_oidc_provider_arn == null ? 0 : 1

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = compact([var.github_oidc_provider_arn])
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository}:environment:${var.github_environment}",
      ]
    }
  }
}

resource "aws_iam_role" "github_actions_deploy" {
  count = var.github_oidc_provider_arn == null ? 0 : 1

  name_prefix        = "${var.name}-github-deploy-"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume[0].json
}

data "aws_iam_policy_document" "github_actions_deploy" {
  count = var.github_oidc_provider_arn == null ? 0 : 1

  statement {
    sid = "ECRAuthorization"

    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "PushReleaseImages"

    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]

    resources = [
      aws_ecr_repository.api.arn,
      aws_ecr_repository.runtime.arn,
    ]
  }

  statement {
    sid = "ReadAndRegisterTaskDefinitions"

    actions = [
      "ecs:DescribeTaskDefinition",
      "ecs:RegisterTaskDefinition",
    ]

    resources = ["*"]
  }

  statement {
    sid = "OperateModelForgeServices"

    actions = [
      "ecs:DescribeServices",
      "ecs:UpdateService",
    ]

    resources = [
      "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/${aws_ecs_cluster.this.name}/api",
      "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/${aws_ecs_cluster.this.name}/go-runtime",
    ]
  }

  statement {
    sid = "RunReleaseMigration"

    actions = ["ecs:RunTask"]

    resources = [
      "arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:task-definition/${var.name}-${var.environment}-migration:*",
    ]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.this.arn]
    }
  }

  statement {
    sid = "InspectReleaseTasks"

    actions   = ["ecs:DescribeTasks"]
    resources = ["*"]

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.this.arn]
    }
  }

  statement {
    sid = "PassModelForgeTaskRoles"

    actions = ["iam:PassRole"]

    resources = [
      aws_iam_role.execution.arn,
      aws_iam_role.api_task.arn,
      aws_iam_role.runtime_task.arn,
    ]
  }
}

resource "aws_iam_role_policy" "github_actions_deploy" {
  count = var.github_oidc_provider_arn == null ? 0 : 1

  name   = "release-modelforge"
  role   = aws_iam_role.github_actions_deploy[0].id
  policy = data.aws_iam_policy_document.github_actions_deploy[0].json
}
