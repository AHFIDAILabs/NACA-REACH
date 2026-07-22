###############################################################################
# NACA AI Chatbot — Cloud Armor Module
# WAF + DDoS protection for the API Gateway
# See: Section 5.1
###############################################################################

variable "project_id" { type = string }
variable "environment" { type = string }
variable "app_name" { type = string }

locals {
  policy_name = "${var.app_name}-waf-${var.environment}"
}

resource "google_compute_security_policy" "waf" {
  name    = local.policy_name
  project = var.project_id

  # Default rule — allow all (deny handled by specific rules)
  rule {
    action   = "allow"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow rule"
  }

  # Block known bad bots and scanners
  rule {
    action   = "deny(403)"
    priority = "1000"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-v33-stable')"
      }
    }
    description = "SQL injection protection"
  }

  rule {
    action   = "deny(403)"
    priority = "1001"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('xss-v33-stable')"
      }
    }
    description = "Cross-site scripting protection"
  }

  rule {
    action   = "deny(403)"
    priority = "1002"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('rfi-v33-stable')"
      }
    }
    description = "Remote file inclusion protection"
  }

  # Rate limiting — 500 requests per minute per IP
  rule {
    action   = "rate_based_ban"
    priority = "2000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      rate_limit_threshold {
        count        = 500
        interval_sec = 60
      }
      ban_duration_sec = 300 # 5-minute ban on exceeding rate limit
    }
    description = "Rate limiting — 500 req/min per IP"
  }

  # Adaptive DDoS protection
  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
    }
  }
}

output "policy_id" {
  value = google_compute_security_policy.waf.id
}

output "policy_name" {
  value = google_compute_security_policy.waf.name
}
