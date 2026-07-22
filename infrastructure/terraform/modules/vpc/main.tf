###############################################################################
# NACA AI Chatbot — VPC Network Module
# Creates VPC, subnets (public, app, data), Cloud NAT, firewall rules
# See: Architecture Document — Section 4, Network Architecture
###############################################################################

variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "app_name" { type = string }

locals {
  vpc_name = "${var.app_name}-vpc-${var.environment}"
}

# ── VPC ──────────────────────────────────────────────────────────────────────

resource "google_compute_network" "main" {
  name                    = local.vpc_name
  project                 = var.project_id
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

# ── Subnets ──────────────────────────────────────────────────────────────────

resource "google_compute_subnetwork" "public" {
  name          = "${local.vpc_name}-public"
  project       = var.project_id
  region        = var.region
  network       = google_compute_network.main.id
  ip_cidr_range = "10.0.1.0/24"

  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_subnetwork" "app" {
  name          = "${local.vpc_name}-app"
  project       = var.project_id
  region        = var.region
  network       = google_compute_network.main.id
  ip_cidr_range = "10.0.2.0/22"

  # GKE secondary ranges for pods and services
  secondary_ip_range {
    range_name    = "gke-pods"
    ip_cidr_range = "10.4.0.0/14"
  }
  secondary_ip_range {
    range_name    = "gke-services"
    ip_cidr_range = "10.8.0.0/20"
  }

  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_subnetwork" "data" {
  name          = "${local.vpc_name}-data"
  project       = var.project_id
  region        = var.region
  network       = google_compute_network.main.id
  ip_cidr_range = "10.0.8.0/22"

  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

# ── Cloud NAT (outbound internet for private subnets) ────────────────────────

resource "google_compute_router" "nat_router" {
  name    = "${local.vpc_name}-nat-router"
  project = var.project_id
  region  = var.region
  network = google_compute_network.main.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "${local.vpc_name}-nat"
  project                            = var.project_id
  region                             = var.region
  router                             = google_compute_router.nat_router.name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# ── Firewall Rules ───────────────────────────────────────────────────────────

resource "google_compute_firewall" "allow_health_checks" {
  name    = "${local.vpc_name}-allow-health-checks"
  project = var.project_id
  network = google_compute_network.main.id

  allow {
    protocol = "tcp"
    ports    = ["8000", "443"]
  }

  # Google health check IP ranges
  source_ranges = ["35.191.0.0/16", "130.211.0.0/22"]
  target_tags   = ["gke-node"]
}

resource "google_compute_firewall" "deny_all_ingress" {
  name     = "${local.vpc_name}-deny-all-ingress"
  project  = var.project_id
  network  = google_compute_network.main.id
  priority = 65534

  deny {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "vpc_id" {
  value = google_compute_network.main.id
}

output "vpc_name" {
  value = google_compute_network.main.name
}

output "app_subnet_id" {
  value = google_compute_subnetwork.app.id
}

output "app_subnet_name" {
  value = google_compute_subnetwork.app.name
}

output "data_subnet_id" {
  value = google_compute_subnetwork.data.id
}
