"""
PostgreSQL Database Service - For production deployment
Uses psycopg2 for PostgreSQL connection
"""
import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

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
    """PostgreSQL Database Service for production"""
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        database: str = None,
        user: str = None,
        password: str = None,
        min_connections: int = 1,
        max_connections: int = 10
    ):
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2 is required for PostgreSQL. Install with: pip install psycopg2-binary")
        
        # Load from environment if not provided
        self.host = host or os.getenv('POSTGRES_HOST', 'localhost')
        self.port = port or int(os.getenv('POSTGRES_PORT', 5432))
        self.database = database or os.getenv('POSTGRES_DB', 'email_agent')
        self.user = user or os.getenv('POSTGRES_USER', 'postgres')
        self.password = password or os.getenv('POSTGRES_PASSWORD', '')
        
        # Create connection pool
        self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
            min_connections,
            max_connections,
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password
        )
        
        self._init_database()
        logger.info(f"PostgreSQL connected to {self.host}:{self.port}/{self.database}")
    
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
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sent_emails_recipient ON sent_emails(recipient_email)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sent_emails_response ON sent_emails(response_received)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cv_evaluations_status ON cv_evaluations(status)")
            
            logger.info("PostgreSQL database initialized")
    
    # ==================== Raw Query Methods ====================
    
    def execute_raw(self, query: str, params: tuple = None):
        """Execute a raw SQL query"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
    
    def query_raw(self, query: str, params: tuple = None, one: bool = False) -> Optional[Any]:
        """Execute a query and return results"""
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
    
    def close(self):
        """Close all connections"""
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("PostgreSQL connections closed")
