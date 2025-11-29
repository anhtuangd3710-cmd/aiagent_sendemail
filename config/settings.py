"""
Configuration settings for the Email AI Agent
Supports both Azure OpenAI and Google Gemini
Supports SQLite (dev) and PostgreSQL (production)
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ===========================================
# AI Provider Selection
# Set to "azure" or "gemini"
# ===========================================
AI_PROVIDER = os.getenv("AI_PROVIDER", "azure").lower()

# ===========================================
# Azure OpenAI Configuration
# ===========================================
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

# ===========================================
# Google Gemini Configuration
# ===========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Available models: gemini-1.5-flash, gemini-1.5-pro, gemini-pro

# ===========================================
# Email Configuration (Gmail IMAP/SMTP)
# ===========================================
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", 993))

# User A (Sender) Configuration
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")  # App password for Gmail

# ===========================================
# Monitoring Configuration
# ===========================================
# Check interval for monitoring responses (in seconds)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 10))

# Realtime mode - sử dụng IMAP IDLE nếu có thể
REALTIME_MODE = os.getenv("REALTIME_MODE", "true").lower() == "true"

# Auto-start monitor when app starts (no user action needed)
AUTO_START_MONITOR = os.getenv("AUTO_START_MONITOR", "true").lower() == "true"

# ===========================================
# Database Configuration
# ===========================================
# Database type: "sqlite" or "postgres"
DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite").lower()

# SQLite Configuration (default for development)
DATABASE_PATH = os.getenv("DATABASE_PATH", "email_tracking.db")

# PostgreSQL Configuration (for production)
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "email_agent")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

# ===========================================
# Security Configuration
# ===========================================
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")


