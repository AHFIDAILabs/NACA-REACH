###############################################################################
# NACA AI Chatbot — Staging Environment
# Composes all infrastructure modules for the staging GCP project
# See: Section 6.1 — Step 04 deliverable
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.20"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Terraform state stored in GCS bucket (created manually first)
  backend "gcs" {
    bucket = "naca-chatbot-tfstate-staging"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Variables ────────────────────────────────────────────────────────────────

variable "project_id" {
  default = "naca-chatbot-staging"
}

variable "region" {
  default = "africa-south1"
}

locals {
  environment = "staging"
  app_name    = "naca-chatbot"
}

# ── Enable Required APIs ────────────────────────────────────────────────────

resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "translate.googleapis.com",
    "aiplatform.googleapis.com",
    "servicenetworking.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "artifactregistry.googleapis.com",
    "clouddeploy.googleapis.com",
  ])

  project = var.project_id
  service = each.value

  disable_dependent_services = false
  disable_on_destroy         = false
}

# ── VPC Network ──────────────────────────────────────────────────────────────

module "vpc" {
  source      = "../../modules/vpc"
  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  app_name    = local.app_name

  depends_on = [google_project_service.apis]
}

# ── GKE Autopilot ────────────────────────────────────────────────────────────

module "gke" {
  source      = "../../modules/gke"
  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  app_name    = local.app_name
  vpc_name    = module.vpc.vpc_name
  subnet_name = module.vpc.app_subnet_name

  depends_on = [module.vpc]
}

# ── Cloud SQL (PostgreSQL + PostGIS) ─────────────────────────────────────────

module "cloudsql" {
  source      = "../../modules/cloudsql"
  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  app_name    = local.app_name
  vpc_id      = module.vpc.vpc_id

  db_tier         = "db-custom-2-8192" # 2 vCPU, 8GB
  db_disk_size_gb = 20

  depends_on = [module.vpc]
}

# ── Memorystore for Redis ────────────────────────────────────────────────────

module "redis" {
  source      = "../../modules/redis"
  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  app_name    = local.app_name
  vpc_id      = module.vpc.vpc_id

  memory_size_gb = 1

  depends_on = [module.vpc]
}

# ── Cloud Storage ────────────────────────────────────────────────────────────

module "storage" {
  source      = "../../modules/storage"
  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  app_name    = local.app_name

  depends_on = [google_project_service.apis]
}

# ── BigQuery Analytics ───────────────────────────────────────────────────────

module "bigquery" {
  source      = "../../modules/bigquery"
  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  app_name    = local.app_name

  depends_on = [google_project_service.apis]
}

# ── Cloud Armor (WAF + DDoS) ────────────────────────────────────────────────

module "cloud_armor" {
  source      = "../../modules/cloud_armor"
  project_id  = var.project_id
  environment = local.environment
  app_name    = local.app_name

  depends_on = [google_project_service.apis]
}

# ── Secret Manager ───────────────────────────────────────────────────────────

module "secrets" {
  source      = "../../modules/secrets"
  project_id  = var.project_id
  environment = local.environment
  app_name    = local.app_name

  depends_on = [google_project_service.apis]
}

# ── Artifact Registry ────────────────────────────────────────────────────────

resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  project       = var.project_id
  repository_id = "${local.app_name}-docker"
  format        = "DOCKER"
  description   = "NACA Chatbot container images"

  docker_config {
    immutable_tags = false
  }

  depends_on = [google_project_service.apis]
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "gke_cluster_name" {
  value = module.gke.cluster_name
}

output "cloudsql_instance" {
  value = module.cloudsql.instance_connection_name
}

output "cloudsql_private_ip" {
  value     = module.cloudsql.private_ip
  sensitive = true
}

output "redis_host" {
  value = module.redis.host
}

output "bigquery_dataset" {
  value = module.bigquery.dataset_id
}

output "knowledge_base_bucket" {
  value = module.storage.knowledge_base_bucket
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
}
