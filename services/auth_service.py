"""
Authentication Service - User registration, login, and session management
"""
import hashlib
import secrets
import re
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from functools import wraps
from flask import request, jsonify, session
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Detect if using PostgreSQL
IS_POSTGRES = bool(os.getenv('DATABASE_URL'))


class AuthService:
    """Service for user authentication"""
    
    def __init__(self, database_service):
        self.db = database_service
        self._init_auth_tables()
    
    def _init_auth_tables(self):
        """Initialize authentication tables"""
        if IS_POSTGRES:
            # PostgreSQL syntax
            self.db.execute_raw("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    salt VARCHAR(255) NOT NULL,
                    full_name VARCHAR(255),
                    role VARCHAR(50) DEFAULT 'user',
                    is_active BOOLEAN DEFAULT TRUE,
                    email_verified BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
            
            self.db.execute_raw("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token VARCHAR(255) UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address VARCHAR(50),
                    user_agent TEXT
                )
            """)
            
            self.db.execute_raw("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token VARCHAR(255) UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            # SQLite syntax
            self.db.execute_raw("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    full_name TEXT,
                    role TEXT DEFAULT 'user',
                    is_active BOOLEAN DEFAULT TRUE,
                    email_verified BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
            
            self.db.execute_raw("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address TEXT,
                    user_agent TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            self.db.execute_raw("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
        
        logger.info("Auth tables initialized")
    
    def _hash_password(self, password: str, salt: str) -> str:
        """Hash password with salt using SHA-256"""
        return hashlib.sha256((password + salt).encode()).hexdigest()
    
    def _generate_salt(self) -> str:
        """Generate a random salt"""
        return secrets.token_hex(32)
    
    def _generate_token(self) -> str:
        """Generate a secure random token"""
        return secrets.token_urlsafe(64)
    
    def _validate_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def _validate_password(self, password: str) -> Tuple[bool, str]:
        """Validate password strength"""
        if len(password) < 8:
            return False, "Mật khẩu phải có ít nhất 8 ký tự"
        if not re.search(r'[A-Z]', password):
            return False, "Mật khẩu phải có ít nhất 1 chữ hoa"
        if not re.search(r'[a-z]', password):
            return False, "Mật khẩu phải có ít nhất 1 chữ thường"
        if not re.search(r'\d', password):
            return False, "Mật khẩu phải có ít nhất 1 số"
        return True, ""
    
    def register(
        self,
        username: str,
        email: str,
        password: str,
        full_name: Optional[str] = None
    ) -> Dict:
        """Register a new user"""
        # Validate inputs
        if not username or len(username) < 3:
            return {"success": False, "error": "Username phải có ít nhất 3 ký tự"}
        
        if not self._validate_email(email):
            return {"success": False, "error": "Email không hợp lệ"}
        
        valid, msg = self._validate_password(password)
        if not valid:
            return {"success": False, "error": msg}
        
        # Check if user exists
        existing = self.db.query_raw(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email)
        )
        if existing:
            return {"success": False, "error": "Username hoặc email đã tồn tại"}
        
        # Create user
        salt = self._generate_salt()
        password_hash = self._hash_password(password, salt)
        
        try:
            user_id = self.db.insert_raw(
                """INSERT INTO users (username, email, password_hash, salt, full_name)
                   VALUES (?, ?, ?, ?, ?)""",
                (username, email, password_hash, salt, full_name)
            )
            
            logger.info(f"User registered: {username}")
            return {
                "success": True,
                "user_id": user_id,
                "message": "Đăng ký thành công!"
            }
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return {"success": False, "error": str(e)}
    
    def login(
        self,
        username_or_email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict:
        """Login user and create session"""
        # Find user
        user = self.db.query_raw(
            """SELECT id, username, email, password_hash, salt, full_name, role, is_active
               FROM users WHERE username = ? OR email = ?""",
            (username_or_email, username_or_email),
            one=True
        )
        
        if not user:
            return {"success": False, "error": "Sai tên đăng nhập hoặc mật khẩu"}
        
        if not user['is_active']:
            return {"success": False, "error": "Tài khoản đã bị vô hiệu hóa"}
        
        # Verify password
        password_hash = self._hash_password(password, user['salt'])
        if password_hash != user['password_hash']:
            return {"success": False, "error": "Sai tên đăng nhập hoặc mật khẩu"}
        
        # Create session token
        token = self._generate_token()
        expires_at = datetime.now() + timedelta(days=7)
        
        self.db.insert_raw(
            """INSERT INTO sessions (user_id, token, expires_at, ip_address, user_agent)
               VALUES (?, ?, ?, ?, ?)""",
            (user['id'], token, expires_at.isoformat(), ip_address, user_agent)
        )
        
        # Update last login
        self.db.execute_raw(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now().isoformat(), user['id'])
        )
        
        logger.info(f"User logged in: {user['username']}")
        return {
            "success": True,
            "token": token,
            "user": {
                "id": user['id'],
                "username": user['username'],
                "email": user['email'],
                "full_name": user['full_name'],
                "role": user['role']
            },
            "expires_at": expires_at.isoformat()
        }
    
    def logout(self, token: str) -> Dict:
        """Logout user by invalidating session"""
        self.db.execute_raw("DELETE FROM sessions WHERE token = ?", (token,))
        return {"success": True, "message": "Đăng xuất thành công"}
    
    def validate_token(self, token: str) -> Optional[Dict]:
        """Validate session token and return user info"""
        session_data = self.db.query_raw(
            """SELECT s.*, u.username, u.email, u.full_name, u.role, u.is_active
               FROM sessions s
               JOIN users u ON s.user_id = u.id
               WHERE s.token = ? AND s.expires_at > ?""",
            (token, datetime.now().isoformat()),
            one=True
        )
        
        if not session_data or not session_data['is_active']:
            return None
        
        return {
            "id": session_data['user_id'],
            "username": session_data['username'],
            "email": session_data['email'],
            "full_name": session_data['full_name'],
            "role": session_data['role']
        }
    
    def change_password(self, user_id: int, old_password: str, new_password: str) -> Dict:
        """Change user password"""
        user = self.db.query_raw(
            "SELECT password_hash, salt FROM users WHERE id = ?",
            (user_id,),
            one=True
        )
        
        if not user:
            return {"success": False, "error": "User không tồn tại"}
        
        # Verify old password
        old_hash = self._hash_password(old_password, user['salt'])
        if old_hash != user['password_hash']:
            return {"success": False, "error": "Mật khẩu cũ không đúng"}
        
        # Validate new password
        valid, msg = self._validate_password(new_password)
        if not valid:
            return {"success": False, "error": msg}
        
        # Update password
        new_salt = self._generate_salt()
        new_hash = self._hash_password(new_password, new_salt)
        
        self.db.execute_raw(
            "UPDATE users SET password_hash = ?, salt = ?, updated_at = ? WHERE id = ?",
            (new_hash, new_salt, datetime.now().isoformat(), user_id)
        )
        
        # Invalidate all sessions
        self.db.execute_raw("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        
        return {"success": True, "message": "Đổi mật khẩu thành công"}
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        user = self.db.query_raw(
            """SELECT id, username, email, full_name, role, is_active, 
                      email_verified, created_at, last_login
               FROM users WHERE id = ?""",
            (user_id,),
            one=True
        )
        return user
    
    def update_profile(self, user_id: int, full_name: Optional[str] = None, email: Optional[str] = None) -> Dict:
        """Update user profile"""
        updates = []
        params = []
        
        if full_name is not None:
            updates.append("full_name = ?")
            params.append(full_name)
        
        if email is not None:
            if not self._validate_email(email):
                return {"success": False, "error": "Email không hợp lệ"}
            # Check if email exists
            existing = self.db.query_raw(
                "SELECT id FROM users WHERE email = ? AND id != ?",
                (email, user_id)
            )
            if existing:
                return {"success": False, "error": "Email đã được sử dụng"}
            updates.append("email = ?")
            params.append(email)
        
        if not updates:
            return {"success": False, "error": "Không có thông tin cần cập nhật"}
        
        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(user_id)
        
        self.db.execute_raw(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            tuple(params)
        )
        
        return {"success": True, "message": "Cập nhật thành công"}
    
    def get_all_users(self) -> list:
        """Get all users (admin only)"""
        users = self.db.query_raw(
            """SELECT id, username, email, full_name, role, is_active, 
                      email_verified, created_at, last_login
               FROM users ORDER BY created_at DESC"""
        )
        return users or []
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        self.db.execute_raw(
            "DELETE FROM sessions WHERE expires_at < ?",
            (datetime.now().isoformat(),)
        )


def login_required(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            token = request.cookies.get('auth_token')
        
        if not token:
            return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
        
        # Get auth service from app context
        from flask import current_app
        auth_service = current_app.config.get('auth_service')
        if not auth_service:
            return jsonify({"success": False, "error": "Auth service not configured"}), 500
        
        user = auth_service.validate_token(token)
        if not user:
            return jsonify({"success": False, "error": "Phiên đăng nhập hết hạn"}), 401
        
        # Add user to request context
        request.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if request.current_user.get('role') != 'admin':
            return jsonify({"success": False, "error": "Không có quyền truy cập"}), 403
        return f(*args, **kwargs)
    return decorated_function
