###############################################################################
# NACA AI Chatbot — Secret Manager Module
# All application secrets stored in GCP Secret Manager
# Accessed via Workload Identity — no keys in code or env vars
# See: Section 2.3
###############################################################################

variable "project_id" { type = string }
variable "environment" { type = string }
variable "app_name" { type = string }

locals {
  prefix = "${var.app_name}-${var.environment}"

  # All secrets needed by the application
  secret_names = [
    "anthropic-api-key",
    "whatsapp-api-token",
    "whatsapp-app-secret",
    "whatsapp-verify-token",
    "telegram-bot-token",
    "telegram-webhook-secret",
    "google-maps-api-key",
    "jwt-secret-key",
    "internal-service-token",
    "pagerduty-integration-key",
  ]
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = toset(local.secret_names)
  secret_id = "${local.prefix}-${each.value}"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    application = var.app_name
  }
}

# Note: Secret values are NOT set by Terraform — they are populated
# manually or via a secure CI/CD process after initial provisioning.
# This prevents secrets from being stored in Terraform state.

output "secret_ids" {
  value = { for k, v in google_secret_manager_secret.secrets : k => v.secret_id }
}
