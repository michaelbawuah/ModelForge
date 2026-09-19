resource "aws_ecs_cluster" "this" {
  name = "${var.name}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.name}/${var.environment}/api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "runtime" {
  name              = "/ecs/${var.name}/${var.environment}/go-runtime"
  retention_in_days = var.log_retention_days
}

resource "aws_service_discovery_private_dns_namespace" "this" {
  name = var.private_dns_namespace
  vpc  = aws_vpc.this.id
}

resource "aws_service_discovery_service" "runtime" {
  name = "go-runtime"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.this.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_ecs_task_definition" "runtime" {
  family                   = "${var.name}-${var.environment}-go-runtime"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.runtime_cpu)
  memory                   = tostring(var.runtime_memory)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.runtime_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "go-runtime"
      image     = local.runtime_image
      essential = true

      portMappings = [
        {
          containerPort = 8090
          hostPort      = 8090
          protocol      = "tcp"
        }
      ]

      secrets = [
        {
          name      = "MODELFORGE_RUNTIME_TOKEN"
          valueFrom = aws_secretsmanager_secret.runtime_token.arn
        }
      ]

      healthCheck = {
        command = [
          "CMD-SHELL",
          "wget -qO- --header=\"Authorization: Bearer $MODELFORGE_RUNTIME_TOKEN\" http://127.0.0.1:8090/health >/dev/null || exit 1",
        ]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 10
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.runtime.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "runtime"
        }
      }
    }
  ])
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-${var.environment}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.api_cpu)
  memory                   = tostring(var.api_memory)
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.api_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = local.api_image
      essential = true

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      environment = local.api_environment
      secrets     = local.api_secrets

      healthCheck = {
        command = [
          "CMD-SHELL",
          "python -c 'import urllib.request; urllib.request.urlopen(\"http://127.0.0.1:8000/health\", timeout=2).read()' || exit 1",
        ]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
    }
  ])
}

resource "aws_ecs_task_definition" "migration" {
  family                   = "${var.name}-${var.environment}-migration"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.api_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "migration"
      image     = local.api_image
      essential = true

      command = [
        "/bin/sh",
        "-c",
        "python -m modelforge.core.database_ready && alembic upgrade head",
      ]

      environment = local.api_environment
      secrets     = local.api_secrets

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "migration"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "runtime" {
  name            = "go-runtime"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.runtime.arn
  desired_count   = var.activate_services ? var.runtime_desired_count : 0
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = [for subnet in aws_subnet.app : subnet.id]
    security_groups  = [aws_security_group.runtime.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.runtime.arn
  }
}

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.activate_services ? var.api_desired_count : 0
  launch_type     = "FARGATE"

  health_check_grace_period_seconds = 90

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = [for subnet in aws_subnet.app : subnet.id]
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [
    aws_lb_listener.https,
    aws_ecs_service.runtime,
  ]
}
