###############################################################################
# NACA AI Chatbot — Terraform Root Variables
# Shared variable definitions used across all modules
###############################################################################

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "africa-south1"
}

variable "environment" {
  description = "Environment name: dev, staging, prod"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "app_name" {
  description = "Application name used in resource naming"
  type        = string
  default     = "naca-chatbot"
}
