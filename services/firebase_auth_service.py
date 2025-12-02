"""
Firebase Authentication Service
Handles user authentication with Firebase, including email verification
"""
import os
import logging
from typing import Optional, Dict, Tuple
from functools import wraps
from flask import request, jsonify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import Firebase Admin SDK
try:
    import firebase_admin
    from firebase_admin import credentials, auth as firebase_auth
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    logger.warning("firebase-admin not installed. Run: pip install firebase-admin")

from config.firebase_config import (
    FIREBASE_SERVICE_ACCOUNT, 
    FIREBASE_ADMIN_CREDENTIALS,
    is_firebase_admin_configured
)


class FirebaseAuthService:
    """Service for Firebase Authentication"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, database_service=None):
        """Initialize Firebase Admin SDK"""
        if self._initialized:
            return
            
        self.db = database_service
        self.firebase_app = None
        
        if not FIREBASE_AVAILABLE:
            logger.error("Firebase Admin SDK not available")
            return
        
        try:
            # Check if already initialized
            try:
                self.firebase_app = firebase_admin.get_app()
                logger.info("✅ Firebase Admin SDK already initialized")
            except ValueError:
                # Not initialized yet, initialize now
                if FIREBASE_ADMIN_CREDENTIALS and os.path.exists(FIREBASE_ADMIN_CREDENTIALS):
                    # Use service account JSON file
                    cred = credentials.Certificate(FIREBASE_ADMIN_CREDENTIALS)
                    logger.info(f"Using Firebase credentials from file: {FIREBASE_ADMIN_CREDENTIALS}")
                elif is_firebase_admin_configured():
                    # Use environment variables
                    cred = credentials.Certificate(FIREBASE_SERVICE_ACCOUNT)
                    logger.info("Using Firebase credentials from environment variables")
                else:
                    logger.warning("⚠️ Firebase Admin credentials not configured")
                    return
                
                self.firebase_app = firebase_admin.initialize_app(cred)
                logger.info("✅ Firebase Admin SDK initialized successfully")
            
            self._initialized = True
            
            # Initialize database tables for Firebase users
            if self.db:
                self._init_firebase_tables()
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize Firebase Admin SDK: {e}")
    
    def _init_firebase_tables(self):
        """Initialize database tables for Firebase users"""
        IS_POSTGRES = bool(os.getenv('DATABASE_URL'))
        
        if IS_POSTGRES:
            self.db.execute_raw("""
                CREATE TABLE IF NOT EXISTS firebase_users (
                    id SERIAL PRIMARY KEY,
                    firebase_uid VARCHAR(128) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    email_verified BOOLEAN DEFAULT FALSE,
                    display_name VARCHAR(255),
                    photo_url TEXT,
                    provider VARCHAR(50) DEFAULT 'password',
                    role VARCHAR(50) DEFAULT 'user',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
        else:
            self.db.execute_raw("""
                CREATE TABLE IF NOT EXISTS firebase_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    firebase_uid TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    email_verified BOOLEAN DEFAULT FALSE,
                    display_name TEXT,
                    photo_url TEXT,
                    provider TEXT DEFAULT 'password',
                    role TEXT DEFAULT 'user',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
        logger.info("✅ Firebase users table initialized")
    
    def is_available(self) -> bool:
        """Check if Firebase is available and configured"""
        return FIREBASE_AVAILABLE and self._initialized and self.firebase_app is not None
    
    def verify_id_token(self, id_token: str) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Verify Firebase ID token from client
        Returns: (success, user_data, error_message)
        """
        if not self.is_available():
            return False, None, "Firebase not configured"
        
        try:
            # Verify the ID token
            decoded_token = firebase_auth.verify_id_token(id_token)
            
            user_data = {
                'uid': decoded_token['uid'],
                'email': decoded_token.get('email', ''),
                'email_verified': decoded_token.get('email_verified', False),
                'name': decoded_token.get('name', ''),
                'picture': decoded_token.get('picture', ''),
                'provider': decoded_token.get('firebase', {}).get('sign_in_provider', 'password')
            }
            
            return True, user_data, None
            
        except firebase_auth.ExpiredIdTokenError:
            return False, None, "Token đã hết hạn. Vui lòng đăng nhập lại."
        except firebase_auth.InvalidIdTokenError:
            return False, None, "Token không hợp lệ."
        except firebase_auth.RevokedIdTokenError:
            return False, None, "Token đã bị thu hồi. Vui lòng đăng nhập lại."
        except Exception as e:
            logger.error(f"Error verifying Firebase token: {e}")
            return False, None, f"Lỗi xác thực: {str(e)}"
    
    def get_or_create_user(self, firebase_user: Dict) -> Optional[Dict]:
        """
        Get existing user or create new one from Firebase data
        """
        if not self.db:
            return firebase_user
        
        try:
            uid = firebase_user['uid']
            
            # Check if user exists
            existing = self.db.execute_raw(
                "SELECT * FROM firebase_users WHERE firebase_uid = %s" if os.getenv('DATABASE_URL')
                else "SELECT * FROM firebase_users WHERE firebase_uid = ?",
                (uid,)
            )
            
            if existing:
                # Update last login
                self.db.execute_raw(
                    "UPDATE firebase_users SET last_login = CURRENT_TIMESTAMP, email_verified = %s WHERE firebase_uid = %s"
                    if os.getenv('DATABASE_URL')
                    else "UPDATE firebase_users SET last_login = CURRENT_TIMESTAMP, email_verified = ? WHERE firebase_uid = ?",
                    (firebase_user['email_verified'], uid)
                )
                
                user = existing[0] if isinstance(existing, list) else existing
                return {
                    'id': user['id'] if isinstance(user, dict) else user[0],
                    'firebase_uid': uid,
                    'email': firebase_user['email'],
                    'email_verified': firebase_user['email_verified'],
                    'display_name': firebase_user.get('name', ''),
                    'photo_url': firebase_user.get('picture', ''),
                    'role': user['role'] if isinstance(user, dict) else user[7]
                }
            else:
                # Create new user
                self.db.execute_raw(
                    """INSERT INTO firebase_users 
                       (firebase_uid, email, email_verified, display_name, photo_url, provider, last_login)
                       VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)"""
                    if os.getenv('DATABASE_URL')
                    else """INSERT INTO firebase_users 
                           (firebase_uid, email, email_verified, display_name, photo_url, provider, last_login)
                           VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    (
                        uid,
                        firebase_user['email'],
                        firebase_user['email_verified'],
                        firebase_user.get('name', ''),
                        firebase_user.get('picture', ''),
                        firebase_user.get('provider', 'password')
                    )
                )
                
                return {
                    'firebase_uid': uid,
                    'email': firebase_user['email'],
                    'email_verified': firebase_user['email_verified'],
                    'display_name': firebase_user.get('name', ''),
                    'photo_url': firebase_user.get('picture', ''),
                    'role': 'user'
                }
                
        except Exception as e:
            logger.error(f"Error in get_or_create_user: {e}")
            return firebase_user
    
    def send_email_verification(self, email: str) -> Tuple[bool, Optional[str]]:
        """
        Generate email verification link (send from client-side is recommended)
        """
        if not self.is_available():
            return False, "Firebase not configured"
        
        try:
            # Generate verification link
            link = firebase_auth.generate_email_verification_link(email)
            return True, link
        except firebase_auth.UserNotFoundError:
            return False, "Không tìm thấy người dùng với email này"
        except Exception as e:
            logger.error(f"Error generating verification link: {e}")
            return False, str(e)
    
    def send_password_reset(self, email: str) -> Tuple[bool, Optional[str]]:
        """
        Generate password reset link
        """
        if not self.is_available():
            return False, "Firebase not configured"
        
        try:
            link = firebase_auth.generate_password_reset_link(email)
            return True, link
        except firebase_auth.UserNotFoundError:
            return False, "Không tìm thấy người dùng với email này"
        except Exception as e:
            logger.error(f"Error generating password reset link: {e}")
            return False, str(e)
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get Firebase user by email"""
        if not self.is_available():
            return None
        
        try:
            user = firebase_auth.get_user_by_email(email)
            return {
                'uid': user.uid,
                'email': user.email,
                'email_verified': user.email_verified,
                'display_name': user.display_name,
                'photo_url': user.photo_url,
                'disabled': user.disabled
            }
        except firebase_auth.UserNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error getting user by email: {e}")
            return None
    
    def check_email_verified(self, uid: str) -> bool:
        """Check if user's email is verified"""
        if not self.is_available():
            return False
        
        try:
            user = firebase_auth.get_user(uid)
            return user.email_verified
        except Exception as e:
            logger.error(f"Error checking email verification: {e}")
            return False
    
    def create_user(self, email: str, password: str, display_name: str = None) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        Create new Firebase user (admin operation)
        Note: Usually users register from client-side
        """
        if not self.is_available():
            return False, None, "Firebase not configured"
        
        try:
            user = firebase_auth.create_user(
                email=email,
                password=password,
                display_name=display_name,
                email_verified=False
            )
            
            return True, {
                'uid': user.uid,
                'email': user.email,
                'display_name': user.display_name
            }, None
            
        except firebase_auth.EmailAlreadyExistsError:
            return False, None, "Email này đã được sử dụng"
        except Exception as e:
            logger.error(f"Error creating Firebase user: {e}")
            return False, None, str(e)
    
    def delete_user(self, uid: str) -> Tuple[bool, Optional[str]]:
        """Delete Firebase user"""
        if not self.is_available():
            return False, "Firebase not configured"
        
        try:
            firebase_auth.delete_user(uid)
            
            # Also delete from local database
            if self.db:
                self.db.execute_raw(
                    "DELETE FROM firebase_users WHERE firebase_uid = %s" if os.getenv('DATABASE_URL')
                    else "DELETE FROM firebase_users WHERE firebase_uid = ?",
                    (uid,)
                )
            
            return True, None
        except Exception as e:
            logger.error(f"Error deleting Firebase user: {e}")
            return False, str(e)
    
    def update_user(self, uid: str, **kwargs) -> Tuple[bool, Optional[str]]:
        """Update Firebase user properties"""
        if not self.is_available():
            return False, "Firebase not configured"
        
        try:
            firebase_auth.update_user(uid, **kwargs)
            return True, None
        except Exception as e:
            logger.error(f"Error updating Firebase user: {e}")
            return False, str(e)


# Decorator for Firebase authentication required
def firebase_login_required(f):
    """Decorator to require Firebase authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return jsonify({
                'success': False,
                'error': 'Token không được cung cấp',
                'code': 'NO_TOKEN'
            }), 401
        
        token = auth_header.replace('Bearer ', '')
        
        # Get Firebase service instance
        firebase_service = FirebaseAuthService()
        
        if not firebase_service.is_available():
            return jsonify({
                'success': False,
                'error': 'Firebase chưa được cấu hình',
                'code': 'FIREBASE_NOT_CONFIGURED'
            }), 500
        
        # Verify token
        success, user_data, error = firebase_service.verify_id_token(token)
        
        if not success:
            return jsonify({
                'success': False,
                'error': error,
                'code': 'INVALID_TOKEN'
            }), 401
        
        # Add user data to request context
        request.firebase_user = user_data
        
        return f(*args, **kwargs)
    
    return decorated_function


def firebase_email_verified_required(f):
    """Decorator to require email verification"""
    @wraps(f)
    @firebase_login_required
    def decorated_function(*args, **kwargs):
        user = getattr(request, 'firebase_user', None)
        
        if not user or not user.get('email_verified'):
            return jsonify({
                'success': False,
                'error': 'Email chưa được xác thực. Vui lòng kiểm tra email và nhấn vào link xác thực.',
                'code': 'EMAIL_NOT_VERIFIED'
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function


# Global instance (will be initialized when needed)
firebase_auth_service = None

def get_firebase_auth_service(database_service=None):
    """Get or create Firebase auth service instance"""
    global firebase_auth_service
    if firebase_auth_service is None:
        firebase_auth_service = FirebaseAuthService(database_service)
    return firebase_auth_service
