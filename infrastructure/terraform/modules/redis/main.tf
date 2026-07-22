###############################################################################
# NACA AI Chatbot — Memorystore for Redis Module
# Session storage with 30-minute sliding TTL
# See: Section 3.1.3
###############################################################################

variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "app_name" { type = string }
variable "vpc_id" { type = string }

variable "memory_size_gb" {
  description = "Redis memory in GB"
  type        = number
  default     = 1
}

locals {
  instance_name = "${var.app_name}-redis-${var.environment}"
}

resource "google_redis_instance" "main" {
  name           = local.instance_name
  project        = var.project_id
  region         = var.region
  tier           = var.environment == "prod" ? "STANDARD_HA" : "BASIC"
  memory_size_gb = var.memory_size_gb
  redis_version  = "REDIS_7_0"

  authorized_network = var.vpc_id

  redis_configs = {
    maxmemory-policy = "allkeys-lru"
    notify-keyspace-events = "Ex" # Keyspace notifications for expired keys
  }

  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time {
        hours   = 2
        minutes = 0
      }
    }
  }

  transit_encryption_mode = "SERVER_AUTHENTICATION"
}

output "host" {
  value = google_redis_instance.main.host
}

output "port" {
  value = google_redis_instance.main.port
}

output "connection_string" {
  value     = "redis://${google_redis_instance.main.host}:${google_redis_instance.main.port}"
  sensitive = true
}
