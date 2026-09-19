resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-${var.environment}"
  subnet_ids = [for subnet in aws_subnet.db : subnet.id]

  tags = {
    Name = "${var.name}-${var.environment}"
  }
}

resource "aws_db_instance" "modelforge" {
  identifier = "${var.name}-${var.environment}"

  engine         = "mysql"
  engine_version = var.mysql_engine_version

  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  port     = 3306

  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  backup_retention_period = 7
  copy_tags_to_snapshot   = true
  deletion_protection     = var.db_deletion_protection
  skip_final_snapshot     = !var.db_deletion_protection

  auto_minor_version_upgrade = true
  apply_immediately           = false
}
