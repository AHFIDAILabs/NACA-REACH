###############################################################################
# NACA AI Chatbot — Cloud SQL Module
# PostgreSQL 15 with PostGIS for facility data and escalation tickets
# See: Section 2.3, 3.4, 6.1
###############################################################################

variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "app_name" { type = string }
variable "vpc_id" { type = string }

variable "db_tier" {
  description = "Cloud SQL machine type"
  type        = string
  default     = "db-custom-2-8192" # 2 vCPU, 8GB RAM
}

variable "db_disk_size_gb" {
  description = "Initial disk size in GB"
  type        = number
  default     = 20
}

locals {
  instance_name = "${var.app_name}-db-${var.environment}"
}

# ── Private Service Connection ───────────────────────────────────────────────

resource "google_compute_global_address" "private_ip_range" {
  name          = "${local.instance_name}-private-ip"
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = var.vpc_id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = var.vpc_id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_range.name]
}

# ── Cloud SQL Instance ───────────────────────────────────────────────────────

resource "google_sql_database_instance" "main" {
  name                = local.instance_name
  project             = var.project_id
  region              = var.region
  database_version    = "POSTGRES_15"
  deletion_protection = var.environment == "prod" ? true : false

  depends_on = [google_service_networking_connection.private_vpc]

  settings {
    tier              = var.db_tier
    disk_size         = var.db_disk_size_gb
    disk_autoresize   = true
    availability_type = var.environment == "prod" ? "REGIONAL" : "ZONAL"

    # Private IP only — no public access
    ip_configuration {
      ipv4_enabled    = false
      private_network = var.vpc_id
      require_ssl     = true

      ssl_mode = "ENCRYPTED_ONLY"
    }

    # Backup configuration
    backup_configuration {
      enabled                        = true
      start_time                     = "02:00" # 2 AM UTC (3 AM WAT)
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = 30
        retention_unit   = "COUNT"
      }
    }

    # Maintenance window — Sunday 3am WAT
    maintenance_window {
      day  = 7 # Sunday
      hour = 2 # 2 AM UTC
    }

    # Database flags
    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    database_flags {
      name  = "log_min_duration_statement"
      value = "1000" # Log queries slower than 1 second
    }

    insights_config {
      query_insights_enabled  = true
      record_application_tags = true
      record_client_address   = false # Privacy
    }
  }
}

# ── Database ─────────────────────────────────────────────────────────────────

resource "google_sql_database" "main" {
  name     = "naca_chatbot"
  project  = var.project_id
  instance = google_sql_database_instance.main.name
}

# ── Database User ────────────────────────────────────────────────────────────

resource "random_password" "db_password" {
  length  = 32
  special = true
}

resource "google_sql_user" "app_user" {
  name     = "naca_app"
  project  = var.project_id
  instance = google_sql_database_instance.main.name
  password = random_password.db_password.result
}

# Store password in Secret Manager
resource "google_secret_manager_secret" "db_password" {
  secret_id = "${var.app_name}-db-password-${var.environment}"
  project   = var.project_id

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "instance_name" {
  value = google_sql_database_instance.main.name
}

output "instance_connection_name" {
  value = google_sql_database_instance.main.connection_name
}

output "private_ip" {
  value = google_sql_database_instance.main.private_ip_address
}

output "database_name" {
  value = google_sql_database.main.name
}

output "db_password_secret_id" {
  value = google_secret_manager_secret.db_password.secret_id
}
