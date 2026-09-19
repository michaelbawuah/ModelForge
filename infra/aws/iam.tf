data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name_prefix        = "${var.name}-execution-"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    sid = "ReadRuntimeAndDatabaseSecrets"

    actions = [
      "secretsmanager:GetSecretValue",
    ]

    resources = local.execution_secret_arns
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "read-modelforge-secrets"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

resource "aws_iam_role" "api_task" {
  name_prefix        = "${var.name}-api-task-"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}

data "aws_iam_policy_document" "api_artifacts" {
  statement {
    sid = "ListArtifactPrefix"

    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        var.artifact_prefix,
        "${var.artifact_prefix}/*",
      ]
    }
  }

  statement {
    sid = "ReadWriteArtifactObjects"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]

    resources = [
      "${aws_s3_bucket.artifacts.arn}/${var.artifact_prefix}/*",
    ]
  }
}

resource "aws_iam_role_policy" "api_artifacts" {
  name   = "artifact-bucket-access"
  role   = aws_iam_role.api_task.id
  policy = data.aws_iam_policy_document.api_artifacts.json
}

resource "aws_iam_role" "runtime_task" {
  name_prefix        = "${var.name}-runtime-task-"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
}
