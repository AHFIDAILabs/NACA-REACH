###############################################################################
# NACA AI Chatbot — GKE Autopilot Module
# Fully managed Kubernetes cluster for all application workloads
# See: Section 2.3, 6.1
###############################################################################

variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "app_name" { type = string }
variable "vpc_name" { type = string }
variable "subnet_name" { type = string }

locals {
  cluster_name = "${var.app_name}-gke-${var.environment}"
}

# ── GKE Autopilot Cluster ───────────────────────────────────────────────────

resource "google_container_cluster" "autopilot" {
  name     = local.cluster_name
  project  = var.project_id
  location = var.region

  # Autopilot mode — fully managed node scaling
  enable_autopilot = true

  network    = var.vpc_name
  subnetwork = var.subnet_name

  ip_allocation_policy {
    cluster_secondary_range_name  = "gke-pods"
    services_secondary_range_name = "gke-services"
  }

  # Private cluster — nodes have no public IPs
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false # Allow kubectl from authorized networks
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # Workload Identity — secretless pod-level GCP API access
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Release channel for automatic upgrades
  release_channel {
    channel = var.environment == "prod" ? "STABLE" : "REGULAR"
  }

  # Maintenance window — off-peak Nigerian time (2am–6am WAT)
  maintenance_policy {
    recurring_window {
      start_time = "2026-01-01T01:00:00Z"
      end_time   = "2026-01-01T05:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }
  }

  # Binary Authorization — enforce signed container images (prod only)
  dynamic "binary_authorization" {
    for_each = var.environment == "prod" ? [1] : []
    content {
      evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
    }
  }

  # Logging and monitoring
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
    managed_prometheus {
      enabled = true
    }
  }

  # Deletion protection for production
  deletion_protection = var.environment == "prod" ? true : false
}

# ── Workload Identity Service Account ────────────────────────────────────────

resource "google_service_account" "workload_identity" {
  account_id   = "${var.app_name}-wi-${var.environment}"
  display_name = "NACA Chatbot Workload Identity (${var.environment})"
  project      = var.project_id
}

# Allow the Kubernetes service account to impersonate the GCP service account
resource "google_service_account_iam_member" "workload_identity_binding" {
  service_account_id = google_service_account.workload_identity.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[default/naca-chatbot]"
}

# Grant necessary permissions to the workload identity SA
resource "google_project_iam_member" "wi_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.workload_identity.email}"
}

resource "google_project_iam_member" "wi_storage_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.workload_identity.email}"
}

resource "google_project_iam_member" "wi_bigquery_writer" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.workload_identity.email}"
}

resource "google_project_iam_member" "wi_translate_user" {
  project = var.project_id
  role    = "roles/cloudtranslate.user"
  member  = "serviceAccount:${google_service_account.workload_identity.email}"
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "cluster_name" {
  value = google_container_cluster.autopilot.name
}

output "cluster_endpoint" {
  value     = google_container_cluster.autopilot.endpoint
  sensitive = true
}

output "workload_identity_sa_email" {
  value = google_service_account.workload_identity.email
}
