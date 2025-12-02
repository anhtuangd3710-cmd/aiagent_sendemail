"""
Firebase Configuration
Get your Firebase config from: https://console.firebase.google.com
Project Settings > General > Your apps > Web app > Config
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Firebase Web Config (for frontend)
FIREBASE_CONFIG = {
    "apiKey": os.getenv("FIREBASE_API_KEY", ""),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", ""),
    "projectId": os.getenv("FIREBASE_PROJECT_ID", ""),
    "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", ""),
    "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
    "appId": os.getenv("FIREBASE_APP_ID", "")
}

# Firebase Admin SDK Service Account (for backend verification)
# Download from: Firebase Console > Project Settings > Service Accounts > Generate new private key
FIREBASE_ADMIN_CREDENTIALS = os.getenv("FIREBASE_ADMIN_CREDENTIALS", "")  # Path to service account JSON file

# Or use individual env vars for Vercel (recommended)
FIREBASE_SERVICE_ACCOUNT = {
    "type": "service_account",
    "project_id": os.getenv("FIREBASE_PROJECT_ID", ""),
    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID", ""),
    "private_key": os.getenv("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n"),
    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL", ""),
    "client_id": os.getenv("FIREBASE_CLIENT_ID", ""),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_CERT_URL", "")
}

# Check if Firebase is configured
def is_firebase_configured():
    """Check if Firebase credentials are properly configured"""
    return bool(FIREBASE_CONFIG.get("apiKey")) and bool(FIREBASE_CONFIG.get("projectId"))

def is_firebase_admin_configured():
    """Check if Firebase Admin SDK is configured"""
    return bool(FIREBASE_SERVICE_ACCOUNT.get("project_id")) and bool(FIREBASE_SERVICE_ACCOUNT.get("private_key"))
