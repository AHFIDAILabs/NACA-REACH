###############################################################################
# NACA AI Chatbot — BigQuery Module
# Analytics warehouse for interaction events and programme metrics
# See: Section 3.6
###############################################################################

variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "app_name" { type = string }

locals {
  dataset_id = "naca_chatbot_analytics_${var.environment}"
}

resource "google_bigquery_dataset" "analytics" {
  dataset_id    = local.dataset_id
  project       = var.project_id
  location      = var.region
  friendly_name = "NACA Chatbot Analytics (${var.environment})"
  description   = "Anonymised interaction events and programme metrics"

  default_table_expiration_ms     = 63072000000 # 24 months
  delete_contents_on_destroy      = var.environment != "prod"

  labels = {
    environment = var.environment
    application = var.app_name
  }
}

# ── Interaction Events Table ─────────────────────────────────────────────────

resource "google_bigquery_table" "interaction_events" {
  dataset_id          = google_bigquery_dataset.analytics.dataset_id
  table_id            = "interaction_events"
  project             = var.project_id
  deletion_protection = var.environment == "prod"

  time_partitioning {
    type  = "DAY"
    field = "event_timestamp"
  }

  clustering = ["channel", "state", "intent"]

  schema = jsonencode([
    { name = "event_id", type = "STRING", mode = "REQUIRED" },
    { name = "event_type", type = "STRING", mode = "REQUIRED" },
    { name = "event_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "session_id_hash", type = "STRING", mode = "NULLABLE" },
    { name = "channel", type = "STRING", mode = "NULLABLE" },
    { name = "state", type = "STRING", mode = "NULLABLE" },
    { name = "lga", type = "STRING", mode = "NULLABLE" },
    { name = "language", type = "STRING", mode = "NULLABLE" },
    { name = "intent", type = "STRING", mode = "NULLABLE" },
    { name = "intent_confidence", type = "FLOAT64", mode = "NULLABLE" },
    { name = "model_used", type = "STRING", mode = "NULLABLE" },
    { name = "latency_ms", type = "INT64", mode = "NULLABLE" },
    { name = "escalation_triggered", type = "BOOLEAN", mode = "NULLABLE" },
    { name = "escalation_priority", type = "STRING", mode = "NULLABLE" },
    { name = "referral_requested", type = "BOOLEAN", mode = "NULLABLE" },
    { name = "service_type_requested", type = "STRING", mode = "NULLABLE" },
    { name = "retrieval_confidence", type = "FLOAT64", mode = "NULLABLE" },
    { name = "properties", type = "JSON", mode = "NULLABLE" },
  ])
}

# ── Referral Events Table ────────────────────────────────────────────────────

resource "google_bigquery_table" "referral_events" {
  dataset_id          = google_bigquery_dataset.analytics.dataset_id
  table_id            = "referral_events"
  project             = var.project_id
  deletion_protection = var.environment == "prod"

  time_partitioning {
    type  = "DAY"
    field = "event_timestamp"
  }

  clustering = ["state", "service_type"]

  schema = jsonencode([
    { name = "referral_id", type = "STRING", mode = "REQUIRED" },
    { name = "event_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "session_id_hash", type = "STRING", mode = "NULLABLE" },
    { name = "channel", type = "STRING", mode = "NULLABLE" },
    { name = "state", type = "STRING", mode = "NULLABLE" },
    { name = "lga", type = "STRING", mode = "NULLABLE" },
    { name = "service_type", type = "STRING", mode = "NULLABLE" },
    { name = "facility_id", type = "STRING", mode = "NULLABLE" },
    { name = "search_radius_km", type = "INT64", mode = "NULLABLE" },
    { name = "results_count", type = "INT64", mode = "NULLABLE" },
  ])
}

output "dataset_id" {
  value = google_bigquery_dataset.analytics.dataset_id
}
