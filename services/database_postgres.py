"""
PostgreSQL Database Service - For production deployment
Supports both standard PostgreSQL and Neon Database (serverless PostgreSQL)
Uses psycopg2 for PostgreSQL connection
"""
import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager
from urllib.parse import urlparse

try:
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    print("⚠️ psycopg2 not installed. Install with: pip install psycopg2-binary")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseServicePostgres:
    """PostgreSQL Database Service for production - Supports Neon Database"""
    
    def __init__(
        self,
        database_url: str = None,
        host: str = None,
        port: int = None,
        database: str = None,
        user: str = None,
        password: str = None,
        min_connections: int = 1,
        max_connections: int = 10,
        sslmode: str = None
    ):
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2 is required for PostgreSQL. Install with: pip install psycopg2-binary")
        
        # Priority 1: DATABASE_URL (Neon format)
        # Format: postgresql://user:password@host/database?sslmode=require
        self.database_url = database_url or os.getenv('DATABASE_URL')
        
        if self.database_url:
            # Parse DATABASE_URL (Neon style)
            self._init_from_url(self.database_url, min_connections, max_connections)
        else:
            # Priority 2: Individual parameters
            self.host = host or os.getenv('POSTGRES_HOST', 'localhost')
            self.port = port or int(os.getenv('POSTGRES_PORT', 5432))
            self.database = database or os.getenv('POSTGRES_DB', 'email_agent')
            self.user = user or os.getenv('POSTGRES_USER', 'postgres')
            self.password = password or os.getenv('POSTGRES_PASSWORD', '')
            self.sslmode = sslmode or os.getenv('POSTGRES_SSLMODE', 'prefer')
            
            self._init_connection_pool(min_connections, max_connections)
        
        self._init_database()
    
    def _init_from_url(self, database_url: str, min_connections: int, max_connections: int):
        """Initialize connection from DATABASE_URL (Neon format)"""
        parsed = urlparse(database_url)
        
        self.host = parsed.hostname
        self.port = parsed.port or 5432
        self.database = parsed.path.lstrip('/')
        self.user = parsed.username
        self.password = parsed.password
        
        # Parse query params for sslmode
        query_params = dict(param.split('=') for param in parsed.query.split('&') if '=' in param)
        self.sslmode = query_params.get('sslmode', 'require')  # Neon requires SSL
        
        logger.info(f"🚀 Connecting to Neon Database: {self.host}")
        
        # Create connection pool with SSL for Neon
        self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
            min_connections,
            max_connections,
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            sslmode=self.sslmode
        )
        
        logger.info(f"✅ Neon PostgreSQL connected to {self.host}:{self.port}/{self.database}")
    
    def _init_connection_pool(self, min_connections: int, max_connections: int):
        """Initialize standard PostgreSQL connection pool"""
        # Create connection pool
        self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
            min_connections,
            max_connections,
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            sslmode=self.sslmode
        )
        
        logger.info(f"✅ PostgreSQL connected to {self.host}:{self.port}/{self.database}")
    
    @contextmanager
    def get_connection(self):
        """Get connection from pool"""
        conn = self.connection_pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self.connection_pool.putconn(conn)
    
    def _init_database(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    salt VARCHAR(64) NOT NULL,
                    full_name VARCHAR(255),
                    role VARCHAR(50) DEFAULT 'user',
                    is_active BOOLEAN DEFAULT TRUE,
                    email_verified BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)
            
            # Sessions table
            cursor.execute("""
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
            
            # Sent emails table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sent_emails (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    sender_name VARCHAR(255) NOT NULL,
                    sender_email VARCHAR(255) NOT NULL,
                    recipient_name VARCHAR(255) NOT NULL,
                    recipient_email VARCHAR(255) NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    response_received BOOLEAN DEFAULT FALSE,
                    message_id VARCHAR(255),
                    email_type VARCHAR(50) DEFAULT 'general',
                    cv_evaluation_id INTEGER
                )
            """)
            
            # Responses table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS responses (
                    id SERIAL PRIMARY KEY,
                    sent_email_id INTEGER NOT NULL REFERENCES sent_emails(id) ON DELETE CASCADE,
                    response_subject TEXT,
                    response_body TEXT NOT NULL,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    analysis JSONB,
                    notification_sent BOOLEAN DEFAULT FALSE
                )
            """)
            
            # CV evaluations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cv_evaluations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    candidate_name VARCHAR(255) NOT NULL,
                    candidate_email VARCHAR(255) NOT NULL,
                    job_title VARCHAR(255) NOT NULL,
                    job_requirements TEXT NOT NULL,
                    company_name VARCHAR(255),
                    cv_content TEXT NOT NULL,
                    overall_score DECIMAL(5,2),
                    is_qualified BOOLEAN DEFAULT FALSE,
                    evaluation_result JSONB,
                    email_sent BOOLEAN DEFAULT FALSE,
                    sent_email_id INTEGER REFERENCES sent_emails(id),
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Password reset tokens
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token VARCHAR(255) UNIQUE NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # User settings table - check if needs migration
            # First check if table exists with old structure (setting_key column)
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'user_settings' AND column_name = 'setting_key'
            """)
            old_structure = cursor.fetchone()
            
            if old_structure:
                # Drop old table and recreate with new structure
                logger.info("Migrating user_settings table to new structure...")
                cursor.execute("DROP TABLE IF EXISTS user_settings CASCADE")
            
            # User settings table (for storing API keys, email settings per user)
            # Structure compatible with SQLite version
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    ai_provider VARCHAR(50) DEFAULT 'azure',
                    azure_openai_endpoint TEXT,
                    azure_openai_api_key TEXT,
                    azure_openai_deployment_name TEXT,
                    azure_openai_api_version VARCHAR(50) DEFAULT '2024-02-15-preview',
                    gemini_api_key TEXT,
                    gemini_model VARCHAR(100) DEFAULT 'gemini-1.5-flash',
                    sender_email VARCHAR(255),
                    sender_password TEXT,
                    email_host VARCHAR(255) DEFAULT 'smtp.gmail.com',
                    email_port INTEGER DEFAULT 587,
                    imap_host VARCHAR(255) DEFAULT 'imap.gmail.com',
                    imap_port INTEGER DEFAULT 993,
                    check_interval INTEGER DEFAULT 10,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sent_emails_recipient ON sent_emails(recipient_email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sent_emails_response ON sent_emails(response_received)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cv_evaluations_status ON cv_evaluations(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_settings_user ON user_settings(user_id)")
            
            # Migration: Add parent_email_id and thread_id for conversation threading
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'sent_emails' AND column_name = 'parent_email_id'
            """)
            if not cursor.fetchone():
                logger.info("Adding conversation threading columns to sent_emails...")
                cursor.execute("ALTER TABLE sent_emails ADD COLUMN parent_email_id INTEGER REFERENCES sent_emails(id)")
                cursor.execute("ALTER TABLE sent_emails ADD COLUMN thread_id INTEGER")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_sent_emails_thread ON sent_emails(thread_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_sent_emails_parent ON sent_emails(parent_email_id)")
                logger.info("Conversation threading columns added")
            
            logger.info("PostgreSQL database initialized")
    
    # ==================== Raw Query Methods ====================
    
    def execute_raw(self, query: str, params: tuple = None):
        """Execute a raw SQL query"""
        if not query:
            return
        # Convert SQLite ? placeholders to PostgreSQL %s
        query = query.replace('?', '%s')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
    
    def query_raw(self, query: str, params: tuple = None, one: bool = False) -> Optional[Any]:
        """Execute a query and return results"""
        if not query:
            return None if one else []
        # Convert SQLite ? placeholders to PostgreSQL %s
        query = query.replace('?', '%s')
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params or ())
            if one:
                row = cursor.fetchone()
                return dict(row) if row else None
            rows = cursor.fetchall()
            return [dict(row) for row in rows] if rows else []
    
    def insert_raw(self, query: str, params: tuple = None) -> int:
        """Execute an insert and return the ID"""
        if not query:
            return None
        # Convert SQLite ? placeholders to PostgreSQL %s
        query = query.replace('?', '%s')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Add RETURNING id if not present
            if 'RETURNING' not in query.upper():
                query = query.rstrip(';') + ' RETURNING id'
            cursor.execute(query, params or ())
            result = cursor.fetchone()
            return result[0] if result else None
    
    # ==================== Email Methods ====================
    
    def save_sent_email(
        self,
        sender_name: str,
        sender_email: str,
        recipient_name: str,
        recipient_email: str,
        subject: str,
        body: str,
        purpose: str,
        message_id: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> int:
        """Save a sent email record"""
        return self.insert_raw(
            """INSERT INTO sent_emails 
               (user_id, sender_name, sender_email, recipient_name, recipient_email, 
                subject, body, purpose, message_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (user_id, sender_name, sender_email, recipient_name, recipient_email,
             subject, body, purpose, message_id)
        )
    
    def get_pending_emails(self, user_id: Optional[int] = None) -> List[Dict]:
        """Get emails waiting for responses"""
        if user_id:
            return self.query_raw(
                "SELECT * FROM sent_emails WHERE response_received = FALSE AND user_id = %s",
                (user_id,)
            )
        return self.query_raw("SELECT * FROM sent_emails WHERE response_received = FALSE")
    
    def save_response(
        self,
        sent_email_id: int,
        response_subject: str,
        response_body: str,
        analysis: Dict
    ) -> int:
        """Save a response"""
        response_id = self.insert_raw(
            """INSERT INTO responses (sent_email_id, response_subject, response_body, analysis)
               VALUES (%s, %s, %s, %s)""",
            (sent_email_id, response_subject, response_body, json.dumps(analysis))
        )
        
        self.execute_raw(
            "UPDATE sent_emails SET response_received = TRUE WHERE id = %s",
            (sent_email_id,)
        )
        
        return response_id
    
    def get_email_by_id(self, email_id: int) -> Optional[Dict]:
        """Get email by ID"""
        return self.query_raw(
            "SELECT * FROM sent_emails WHERE id = %s",
            (email_id,),
            one=True
        )
    
    def mark_notification_sent(self, response_id: int):
        """Mark notification as sent"""
        self.execute_raw(
            "UPDATE responses SET notification_sent = TRUE WHERE id = %s",
            (response_id,)
        )
    
    def get_all_emails(self, user_id: Optional[int] = None) -> List[Dict]:
        """Get all emails with responses"""
        query = """
            SELECT se.*, r.response_body, r.analysis, r.received_at as response_received_at
            FROM sent_emails se
            LEFT JOIN responses r ON se.id = r.sent_email_id
        """
        if user_id:
            query += " WHERE se.user_id = %s"
            query += " ORDER BY se.sent_at DESC"
            return self.query_raw(query, (user_id,))
        
        query += " ORDER BY se.sent_at DESC"
        return self.query_raw(query)
    
    def delete_email(self, email_id: int):
        """Delete a sent email and its responses"""
        self.execute_raw("DELETE FROM responses WHERE sent_email_id = %s", (email_id,))
        self.execute_raw("DELETE FROM sent_emails WHERE id = %s", (email_id,))
    
    def delete_emails(self, email_ids: List[int]) -> int:
        """Delete multiple emails by IDs"""
        if not email_ids:
            return 0
        placeholders = ','.join(['%s'] * len(email_ids))
        self.execute_raw(f"DELETE FROM responses WHERE sent_email_id IN ({placeholders})", tuple(email_ids))
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM sent_emails WHERE id IN ({placeholders})", tuple(email_ids))
            return cursor.rowcount
    
    def delete_all_emails(self, user_id: Optional[int] = None) -> int:
        """Delete all sent emails and responses"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT COUNT(*) FROM sent_emails WHERE user_id = %s", (user_id,))
                count = cursor.fetchone()[0]
                cursor.execute("DELETE FROM responses WHERE sent_email_id IN (SELECT id FROM sent_emails WHERE user_id = %s)", (user_id,))
                cursor.execute("DELETE FROM sent_emails WHERE user_id = %s", (user_id,))
            else:
                cursor.execute("SELECT COUNT(*) FROM sent_emails")
                count = cursor.fetchone()[0]
                cursor.execute("DELETE FROM responses")
                cursor.execute("DELETE FROM sent_emails")
            return count
    
    def get_email_count(self, user_id: Optional[int] = None) -> int:
        """Get total number of sent emails"""
        if user_id:
            result = self.query_raw("SELECT COUNT(*) as cnt FROM sent_emails WHERE user_id = %s", (user_id,), one=True)
        else:
            result = self.query_raw("SELECT COUNT(*) as cnt FROM sent_emails", one=True)
        return result['cnt'] if result else 0

    def get_conversation_thread(self, email_id: int) -> List[Dict]:
        """Get all emails in a conversation thread"""
        # First get the thread_id of this email
        email = self.get_email_by_id(email_id)
        if not email:
            return []
        
        thread_id = email.get('thread_id') or email_id
        
        # Get all emails in this thread ordered by sent_at
        query = """
            SELECT se.*, r.response_body, r.response_subject as response_subject, 
                   r.analysis, r.received_at as response_received_at
            FROM sent_emails se
            LEFT JOIN responses r ON se.id = r.sent_email_id
            WHERE se.thread_id = %s OR se.id = %s OR se.parent_email_id = %s
            ORDER BY se.sent_at ASC
        """
        return self.query_raw(query, (thread_id, thread_id, email_id))
    
    def save_reply_email(
        self,
        parent_email_id: int,
        user_id: int,
        sender_name: str,
        sender_email: str,
        recipient_name: str,
        recipient_email: str,
        subject: str,
        body: str,
        purpose: str,
        message_id: str = None
    ) -> int:
        """Save a reply email linked to parent email"""
        # Get the thread_id from parent email
        parent = self.get_email_by_id(parent_email_id)
        thread_id = parent.get('thread_id') or parent_email_id if parent else parent_email_id
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO sent_emails 
                   (user_id, sender_name, sender_email, recipient_name, recipient_email, 
                    subject, body, purpose, message_id, parent_email_id, thread_id, email_type)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'reply')
                   RETURNING id""",
                (user_id, sender_name, sender_email, recipient_name, recipient_email,
                 subject, body, purpose, message_id, parent_email_id, thread_id)
            )
            email_id = cursor.fetchone()[0]
            
            # Update thread_id on parent if not set
            if parent and not parent.get('thread_id'):
                cursor.execute(
                    "UPDATE sent_emails SET thread_id = %s WHERE id = %s",
                    (parent_email_id, parent_email_id)
                )
            
            return email_id
    
    def get_thread_summary(self, thread_id: int) -> Dict:
        """Get summary of a conversation thread"""
        query = """
            SELECT COUNT(*) as total_emails,
                   SUM(CASE WHEN response_received THEN 1 ELSE 0 END) as total_responses,
                   MIN(sent_at) as started_at,
                   MAX(sent_at) as last_activity
            FROM sent_emails
            WHERE thread_id = %s OR id = %s
        """
        return self.query_raw(query, (thread_id, thread_id), one=True)

    # ==================== CV Evaluation Methods ====================
    
    def save_cv_evaluation(
        self,
        candidate_name: str,
        candidate_email: str,
        job_title: str,
        job_requirements: str,
        cv_content: str,
        company_name: Optional[str] = None,
        overall_score: float = 0,
        is_qualified: bool = False,
        evaluation_result: Optional[Dict] = None,
        user_id: Optional[int] = None
    ) -> int:
        """Save CV evaluation"""
        return self.insert_raw(
            """INSERT INTO cv_evaluations 
               (user_id, candidate_name, candidate_email, job_title, job_requirements, 
                cv_content, company_name, overall_score, is_qualified, evaluation_result, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (user_id, candidate_name, candidate_email, job_title, job_requirements,
             cv_content, company_name, overall_score, is_qualified,
             json.dumps(evaluation_result) if evaluation_result else None, 'evaluated')
        )
    
    def get_cv_evaluation_by_id(self, cv_id: int) -> Optional[Dict]:
        """Get CV evaluation by ID"""
        result = self.query_raw(
            "SELECT * FROM cv_evaluations WHERE id = %s",
            (cv_id,),
            one=True
        )
        return result
    
    def get_all_cv_evaluations(self, user_id: Optional[int] = None) -> List[Dict]:
        """Get all CV evaluations"""
        query = """
            SELECT cv.*, se.response_received, r.analysis as response_analysis
            FROM cv_evaluations cv
            LEFT JOIN sent_emails se ON cv.sent_email_id = se.id
            LEFT JOIN responses r ON se.id = r.sent_email_id
        """
        if user_id:
            query += " WHERE cv.user_id = %s"
            query += " ORDER BY cv.created_at DESC"
            return self.query_raw(query, (user_id,))
        
        query += " ORDER BY cv.created_at DESC"
        return self.query_raw(query)
    
    def update_cv_evaluation_email_sent(self, cv_id: int, sent_email_id: int):
        """Update CV when email sent"""
        self.execute_raw(
            """UPDATE cv_evaluations 
               SET email_sent = TRUE, sent_email_id = %s, status = 'email_sent', updated_at = %s
               WHERE id = %s""",
            (sent_email_id, datetime.now().isoformat(), cv_id)
        )
    
    def update_cv_evaluation_status(self, cv_id: int, status: str):
        """Update CV status"""
        self.execute_raw(
            "UPDATE cv_evaluations SET status = %s, updated_at = %s WHERE id = %s",
            (status, datetime.now().isoformat(), cv_id)
        )
    
    def get_qualified_cv_not_emailed(self, user_id: Optional[int] = None) -> List[Dict]:
        """Get qualified CVs not emailed"""
        query = "SELECT * FROM cv_evaluations WHERE is_qualified = TRUE AND email_sent = FALSE"
        if user_id:
            query += " AND user_id = %s"
            return self.query_raw(query, (user_id,))
        return self.query_raw(query)
    
    def allow_resend_email(self, cv_id: int):
        """Allow resending email"""
        self.execute_raw(
            """UPDATE cv_evaluations 
               SET email_sent = FALSE, status = 'allow_resend', updated_at = %s
               WHERE id = %s""",
            (datetime.now().isoformat(), cv_id)
        )
    
    def delete_cv_evaluation(self, cv_id: int):
        """Delete a CV evaluation"""
        self.execute_raw("DELETE FROM cv_evaluations WHERE id = %s", (cv_id,))
    
    def delete_cv_evaluations(self, cv_ids: List[int]) -> int:
        """Delete multiple CV evaluations by IDs"""
        if not cv_ids:
            return 0
        placeholders = ','.join(['%s'] * len(cv_ids))
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM cv_evaluations WHERE id IN ({placeholders})", tuple(cv_ids))
            return cursor.rowcount
    
    def delete_all_cv_evaluations(self, user_id: Optional[int] = None) -> int:
        """Delete all CV evaluations"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT COUNT(*) FROM cv_evaluations WHERE user_id = %s", (user_id,))
                count = cursor.fetchone()[0]
                cursor.execute("DELETE FROM cv_evaluations WHERE user_id = %s", (user_id,))
            else:
                cursor.execute("SELECT COUNT(*) FROM cv_evaluations")
                count = cursor.fetchone()[0]
                cursor.execute("DELETE FROM cv_evaluations")
            return count
    
    def get_cv_count(self, user_id: Optional[int] = None) -> int:
        """Get total number of CV evaluations"""
        if user_id:
            result = self.query_raw("SELECT COUNT(*) as cnt FROM cv_evaluations WHERE user_id = %s", (user_id,), one=True)
        else:
            result = self.query_raw("SELECT COUNT(*) as cnt FROM cv_evaluations", one=True)
        return result['cnt'] if result else 0

    # ==================== User Methods ====================
    
    def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        salt: str,
        full_name: Optional[str] = None,
        role: str = 'user'
    ) -> int:
        """Create a new user"""
        return self.insert_raw(
            """INSERT INTO users (username, email, password_hash, salt, full_name, role)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (username, email, password_hash, salt, full_name, role)
        )
    
    def get_user_by_username_or_email(self, username_or_email: str) -> Optional[Dict]:
        """Get user by username or email"""
        return self.query_raw(
            "SELECT * FROM users WHERE username = %s OR email = %s",
            (username_or_email, username_or_email),
            one=True
        )
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        return self.query_raw(
            "SELECT * FROM users WHERE id = %s",
            (user_id,),
            one=True
        )
    
    def update_user_last_login(self, user_id: int):
        """Update last login time"""
        self.execute_raw(
            "UPDATE users SET last_login = %s WHERE id = %s",
            (datetime.now().isoformat(), user_id)
        )
    
    # ==================== Session Methods ====================
    
    def create_session(
        self,
        user_id: int,
        token: str,
        expires_at: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> int:
        """Create a new session"""
        return self.insert_raw(
            """INSERT INTO sessions (user_id, token, expires_at, ip_address, user_agent)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, token, expires_at, ip_address, user_agent)
        )
    
    def get_session_by_token(self, token: str) -> Optional[Dict]:
        """Get session by token"""
        return self.query_raw(
            """SELECT s.*, u.username, u.email, u.full_name, u.role, u.is_active
               FROM sessions s
               JOIN users u ON s.user_id = u.id
               WHERE s.token = %s AND s.expires_at > %s""",
            (token, datetime.now().isoformat()),
            one=True
        )
    
    def delete_session(self, token: str):
        """Delete a session"""
        self.execute_raw("DELETE FROM sessions WHERE token = %s", (token,))
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        self.execute_raw(
            "DELETE FROM sessions WHERE expires_at < %s",
            (datetime.now().isoformat(),)
        )
    
    # ==================== User Settings Methods ====================
    
    def get_user_settings(self, user_id: int) -> Optional[Dict]:
        """Get all settings for a user - compatible with SQLite version"""
        result = self.query_raw(
            "SELECT * FROM user_settings WHERE user_id = %s",
            (user_id,),
            one=True
        )
        return dict(result) if result else None
    
    def save_user_settings(self, user_id: int, settings: Dict) -> int:
        """Save or update user settings - compatible with SQLite version"""
        existing = self.get_user_settings(user_id)
        
        if existing:
            # Update existing settings
            update_fields = []
            values = []
            
            allowed_fields = [
                'ai_provider', 'azure_openai_endpoint', 'azure_openai_api_key',
                'azure_openai_deployment_name', 'azure_openai_api_version',
                'gemini_api_key', 'gemini_model',
                'sender_email', 'sender_password',
                'email_host', 'email_port', 'imap_host', 'imap_port',
                'check_interval'
            ]
            
            for field in allowed_fields:
                if field in settings:
                    update_fields.append(f"{field} = %s")
                    values.append(settings[field])
            
            if update_fields:
                update_fields.append("updated_at = %s")
                values.append(datetime.now().isoformat())
                values.append(user_id)
                
                self.execute_raw(f"""
                    UPDATE user_settings 
                    SET {', '.join(update_fields)}
                    WHERE user_id = %s
                """, tuple(values))
                return existing['id']
            return existing['id']
        else:
            # Insert new settings
            return self.insert_raw("""
                INSERT INTO user_settings (
                    user_id, ai_provider,
                    azure_openai_endpoint, azure_openai_api_key,
                    azure_openai_deployment_name, azure_openai_api_version,
                    gemini_api_key, gemini_model,
                    sender_email, sender_password,
                    email_host, email_port, imap_host, imap_port,
                    check_interval
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                settings.get('ai_provider', 'azure'),
                settings.get('azure_openai_endpoint'),
                settings.get('azure_openai_api_key'),
                settings.get('azure_openai_deployment_name'),
                settings.get('azure_openai_api_version', '2024-02-15-preview'),
                settings.get('gemini_api_key'),
                settings.get('gemini_model', 'gemini-1.5-flash'),
                settings.get('sender_email'),
                settings.get('sender_password'),
                settings.get('email_host', 'smtp.gmail.com'),
                settings.get('email_port', 587),
                settings.get('imap_host', 'imap.gmail.com'),
                settings.get('imap_port', 993),
                settings.get('check_interval', 10)
            ))
    
    def delete_user_settings(self, user_id: int):
        """Delete user settings"""
        self.execute_raw("DELETE FROM user_settings WHERE user_id = %s", (user_id,))
    
    def close(self):
        """Close all connections"""
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("PostgreSQL connections closed")
