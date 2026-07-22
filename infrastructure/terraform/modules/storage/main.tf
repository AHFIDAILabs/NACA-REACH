###############################################################################
# NACA AI Chatbot — Cloud Storage Module
# GCS buckets for knowledge base documents and Terraform state
###############################################################################

variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "app_name" { type = string }

# ── Knowledge Base Documents Bucket ──────────────────────────────────────────

resource "google_storage_bucket" "knowledge_base" {
  name     = "${var.app_name}-knowledge-base-${var.environment}"
  project  = var.project_id
  location = var.region

  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  versioning {
    enabled = true # Version control for knowledge base documents
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 5 # Keep last 5 versions
    }
    action {
      type = "Delete"
    }
  }

  encryption {
    default_kms_key_name = "" # Uses Google-managed encryption; set to CMEK in prod
  }
}

# ── Terraform State Bucket ───────────────────────────────────────────────────

resource "google_storage_bucket" "terraform_state" {
  name     = "${var.app_name}-tfstate-${var.environment}"
  project  = var.project_id
  location = var.region

  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 10
    }
    action {
      type = "Delete"
    }
  }
}

output "knowledge_base_bucket" {
  value = google_storage_bucket.knowledge_base.name
}

output "terraform_state_bucket" {
  value = google_storage_bucket.terraform_state.name
}
