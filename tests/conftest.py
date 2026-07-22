"""
NACA AI Chatbot — Test Configuration and Fixtures
"""

import os
import pytest

# Set test environment before importing any app modules
os.environ["NACA_ENVIRONMENT"] = "development"
os.environ["NACA_DEBUG"] = "true"
os.environ["NACA_ANTHROPIC_API_KEY"] = "test-key"
os.environ["NACA_TWILIO_ACCOUNT_SID"] = "ACtest123"
os.environ["NACA_TWILIO_AUTH_TOKEN"] = "test-auth-token"
os.environ["NACA_TWILIO_WHATSAPP_NUMBER"] = "whatsapp:+14155238886"
os.environ["NACA_TELEGRAM_WEBHOOK_SECRET"] = ""
os.environ["NACA_INTERNAL_SERVICE_TOKEN"] = "test-service-token"
os.environ["NACA_JWT_SECRET_KEY"] = "test-jwt-secret"
os.environ["NACA_GCP_PROJECT_ID"] = "naca-chatbot-test"
