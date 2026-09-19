resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.name}-${var.environment}"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name}-${var.environment}-igw"
  }
}

resource "aws_subnet" "public" {
  for_each = local.public_subnets

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.key
  cidr_block              = each.value
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.name}-${var.environment}-public-${each.key}"
    Tier = "public"
  }
}

resource "aws_subnet" "app" {
  for_each = local.app_subnets

  vpc_id            = aws_vpc.this.id
  availability_zone = each.key
  cidr_block        = each.value

  tags = {
    Name = "${var.name}-${var.environment}-app-${each.key}"
    Tier = "application"
  }
}

resource "aws_subnet" "db" {
  for_each = local.db_subnets

  vpc_id            = aws_vpc.this.id
  availability_zone = each.key
  cidr_block        = each.value

  tags = {
    Name = "${var.name}-${var.environment}-db-${each.key}"
    Tier = "database"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = {
    Name = "${var.name}-${var.environment}-public"
  }
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count = var.ha_nat_gateways ? length(local.azs) : 1

  domain = "vpc"

  tags = {
    Name = "${var.name}-${var.environment}-nat-${count.index + 1}"
  }
}

resource "aws_nat_gateway" "this" {
  count = var.ha_nat_gateways ? length(local.azs) : 1

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[local.azs[count.index]].id

  depends_on = [aws_internet_gateway.this]

  tags = {
    Name = "${var.name}-${var.environment}-nat-${count.index + 1}"
  }
}

resource "aws_route_table" "app" {
  for_each = aws_subnet.app

  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[
      var.ha_nat_gateways ? index(local.azs, each.key) : 0
    ].id
  }

  tags = {
    Name = "${var.name}-${var.environment}-app-${each.key}"
  }
}

resource "aws_route_table_association" "app" {
  for_each = aws_subnet.app

  subnet_id      = each.value.id
  route_table_id = aws_route_table.app[each.key].id
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [for table in aws_route_table.app : table.id]

  tags = {
    Name = "${var.name}-${var.environment}-s3"
  }
}
