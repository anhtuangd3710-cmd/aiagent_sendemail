"""
Database Service - Tracks sent emails and responses
"""
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
import json
import logging

from config.settings import DATABASE_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for tracking emails and responses in SQLite database"""
    
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._init_database()
        
    def _init_database(self):
        """Initialize the database tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Table for tracking sent emails
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sent_emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_name TEXT NOT NULL,
                    sender_email TEXT NOT NULL,
                    recipient_name TEXT NOT NULL,
                    recipient_email TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    response_received BOOLEAN DEFAULT FALSE,
                    message_id TEXT,
                    email_type TEXT DEFAULT 'general',
                    cv_evaluation_id INTEGER
                )
            """)
            
            # Table for tracking responses
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sent_email_id INTEGER NOT NULL,
                    response_subject TEXT,
                    response_body TEXT NOT NULL,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    analysis TEXT,
                    notification_sent BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (sent_email_id) REFERENCES sent_emails(id)
                )
            """)
            
            # Table for CV evaluations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cv_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_name TEXT NOT NULL,
                    candidate_email TEXT NOT NULL,
                    job_title TEXT NOT NULL,
                    job_requirements TEXT NOT NULL,
                    company_name TEXT,
                    cv_content TEXT NOT NULL,
                    overall_score REAL,
                    is_qualified BOOLEAN DEFAULT FALSE,
                    evaluation_result TEXT,
                    email_sent BOOLEAN DEFAULT FALSE,
                    sent_email_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Table for user settings (API keys, email config per user)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    
                    -- AI Provider settings
                    ai_provider TEXT DEFAULT 'azure',
                    
                    -- Azure OpenAI
                    azure_openai_endpoint TEXT,
                    azure_openai_api_key TEXT,
                    azure_openai_deployment_name TEXT,
                    azure_openai_api_version TEXT DEFAULT '2024-02-15-preview',
                    
                    -- Google Gemini
                    gemini_api_key TEXT,
                    gemini_model TEXT DEFAULT 'gemini-1.5-flash',
                    
                    -- Email Configuration
                    sender_email TEXT,
                    sender_password TEXT,
                    email_host TEXT DEFAULT 'smtp.gmail.com',
                    email_port INTEGER DEFAULT 587,
                    imap_host TEXT DEFAULT 'imap.gmail.com',
                    imap_port INTEGER DEFAULT 993,
                    
                    -- Other settings
                    check_interval INTEGER DEFAULT 10,
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            # Table for chat sessions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT DEFAULT 'New Chat',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            # Table for chat messages
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'bot')),
                    content TEXT NOT NULL,
                    has_chart BOOLEAN DEFAULT FALSE,
                    chart_type TEXT,
                    chart_data TEXT,
                    has_export BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            conn.commit()
            logger.info("Database initialized successfully")
    
    def save_sent_email(
        self,
        sender_name: str,
        sender_email: str,
        recipient_name: str,
        recipient_email: str,
        subject: str,
        body: str,
        purpose: str,
        message_id: Optional[str] = None
    ) -> int:
        """Save a sent email record and return its ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sent_emails 
                (sender_name, sender_email, recipient_name, recipient_email, 
                 subject, body, purpose, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (sender_name, sender_email, recipient_name, recipient_email,
                  subject, body, purpose, message_id))
            conn.commit()
            email_id = cursor.lastrowid
            logger.info(f"Saved sent email with ID: {email_id}")
            return email_id
    
    def get_pending_emails(self) -> List[Dict]:
        """Get all emails waiting for responses"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sent_emails 
                WHERE response_received = FALSE
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def save_response(
        self,
        sent_email_id: int,
        response_subject: str,
        response_body: str,
        analysis: Dict
    ) -> int:
        """Save a response and its analysis"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Save response
            cursor.execute("""
                INSERT INTO responses 
                (sent_email_id, response_subject, response_body, analysis)
                VALUES (?, ?, ?, ?)
            """, (sent_email_id, response_subject, response_body, json.dumps(analysis)))
            
            # Update sent email status
            cursor.execute("""
                UPDATE sent_emails 
                SET response_received = TRUE 
                WHERE id = ?
            """, (sent_email_id,))
            
            conn.commit()
            response_id = cursor.lastrowid
            logger.info(f"Saved response with ID: {response_id}")
            return response_id
    
    def get_email_by_id(self, email_id: int) -> Optional[Dict]:
        """Get a sent email by its ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sent_emails WHERE id = ?", (email_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def mark_notification_sent(self, response_id: int):
        """Mark a notification as sent"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE responses 
                SET notification_sent = TRUE 
                WHERE id = ?
            """, (response_id,))
            conn.commit()
    
    def get_all_emails(self) -> List[Dict]:
        """Get all sent emails with their response status"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT se.*, r.response_body, r.analysis, r.received_at as response_received_at
                FROM sent_emails se
                LEFT JOIN (
                    SELECT sent_email_id, response_body, analysis, received_at,
                           ROW_NUMBER() OVER (PARTITION BY sent_email_id ORDER BY received_at DESC) as rn
                    FROM responses
                ) r ON se.id = r.sent_email_id AND r.rn = 1
                ORDER BY se.sent_at DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def delete_email(self, email_id: int):
        """Delete a sent email and its responses"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Delete responses first
            cursor.execute("DELETE FROM responses WHERE sent_email_id = ?", (email_id,))
            # Delete the email
            cursor.execute("DELETE FROM sent_emails WHERE id = ?", (email_id,))
            conn.commit()
            logger.info(f"Deleted email with ID: {email_id}")
    
    def delete_emails(self, email_ids: List[int]) -> int:
        """Delete multiple emails by IDs"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(email_ids))
            # Delete responses first
            cursor.execute(f"DELETE FROM responses WHERE sent_email_id IN ({placeholders})", email_ids)
            # Delete emails
            cursor.execute(f"DELETE FROM sent_emails WHERE id IN ({placeholders})", email_ids)
            conn.commit()
            deleted_count = cursor.rowcount
            logger.info(f"Deleted {deleted_count} emails")
            return deleted_count
    
    def delete_all_emails(self) -> int:
        """Delete all sent emails and responses"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Count emails first
            cursor.execute("SELECT COUNT(*) FROM sent_emails")
            count = cursor.fetchone()[0]
            # Delete all responses
            cursor.execute("DELETE FROM responses")
            # Delete all emails
            cursor.execute("DELETE FROM sent_emails")
            conn.commit()
            logger.info(f"Deleted all {count} emails")
            return count
    
    def get_email_count(self) -> int:
        """Get total number of sent emails"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sent_emails")
            return cursor.fetchone()[0]

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
        evaluation_result: Optional[Dict] = None
    ) -> int:
        """Save a CV evaluation record"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cv_evaluations 
                (candidate_name, candidate_email, job_title, job_requirements, 
                 cv_content, company_name, overall_score, is_qualified, evaluation_result, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (candidate_name, candidate_email, job_title, job_requirements,
                  cv_content, company_name, overall_score, is_qualified,
                  json.dumps(evaluation_result) if evaluation_result else None, 'evaluated'))
            conn.commit()
            cv_id = cursor.lastrowid
            logger.info(f"Saved CV evaluation with ID: {cv_id}")
            return cv_id
    
    def get_cv_evaluation_by_id(self, cv_id: int) -> Optional[Dict]:
        """Get a CV evaluation by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cv_evaluations WHERE id = ?", (cv_id,))
            row = cursor.fetchone()
            if row:
                result = dict(row)
                if result.get('evaluation_result'):
                    result['evaluation_result'] = json.loads(result['evaluation_result'])
                return result
            return None
    
    def get_all_cv_evaluations(self) -> List[Dict]:
        """Get all CV evaluations"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT cv.*, se.response_received, r.analysis as response_analysis
                FROM cv_evaluations cv
                LEFT JOIN sent_emails se ON cv.sent_email_id = se.id
                LEFT JOIN responses r ON se.id = r.sent_email_id
                ORDER BY cv.created_at DESC
            """)
            rows = cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                if item.get('evaluation_result'):
                    try:
                        item['evaluation_result'] = json.loads(item['evaluation_result'])
                    except:
                        pass
                if item.get('response_analysis'):
                    try:
                        item['response_analysis'] = json.loads(item['response_analysis'])
                    except:
                        pass
                results.append(item)
            return results
    
    def update_cv_evaluation_email_sent(self, cv_id: int, sent_email_id: int):
        """Update CV evaluation when email is sent"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE cv_evaluations 
                SET email_sent = TRUE, sent_email_id = ?, status = 'email_sent', updated_at = ?
                WHERE id = ?
            """, (sent_email_id, datetime.now().isoformat(), cv_id))
            conn.commit()
    
    def update_cv_evaluation_status(self, cv_id: int, status: str):
        """Update CV evaluation status"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE cv_evaluations 
                SET status = ?, updated_at = ?
                WHERE id = ?
            """, (status, datetime.now().isoformat(), cv_id))
            conn.commit()
    
    def get_qualified_cv_not_emailed(self) -> List[Dict]:
        """Get qualified CVs that haven't been emailed yet"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM cv_evaluations 
                WHERE is_qualified = TRUE AND email_sent = FALSE
            """)
            rows = cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                if item.get('evaluation_result'):
                    try:
                        item['evaluation_result'] = json.loads(item['evaluation_result'])
                    except:
                        pass
                results.append(item)
            return results
    
    def allow_resend_email(self, cv_id: int):
        """Allow resending email for a CV evaluation"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE cv_evaluations 
                SET email_sent = FALSE, status = 'allow_resend', updated_at = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), cv_id))
            conn.commit()
    
    def delete_cv_evaluation(self, cv_id: int):
        """Delete a CV evaluation"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cv_evaluations WHERE id = ?", (cv_id,))
            conn.commit()
            logger.info(f"Deleted CV evaluation with ID: {cv_id}")
    
    def delete_cv_evaluations(self, cv_ids: List[int]) -> int:
        """Delete multiple CV evaluations by IDs"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(cv_ids))
            cursor.execute(f"DELETE FROM cv_evaluations WHERE id IN ({placeholders})", cv_ids)
            conn.commit()
            deleted_count = cursor.rowcount
            logger.info(f"Deleted {deleted_count} CV evaluations")
            return deleted_count
    
    def delete_all_cv_evaluations(self) -> int:
        """Delete all CV evaluations"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Count first
            cursor.execute("SELECT COUNT(*) FROM cv_evaluations")
            count = cursor.fetchone()[0]
            # Delete all
            cursor.execute("DELETE FROM cv_evaluations")
            conn.commit()
            logger.info(f"Deleted all {count} CV evaluations")
            return count
    
    def get_cv_count(self) -> int:
        """Get total number of CV evaluations"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM cv_evaluations")
            return cursor.fetchone()[0]

    # ==================== Raw Query Methods (for Auth Service) ====================
    
    def execute_raw(self, query: str, params: tuple = None):
        """Execute a raw SQL query"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            conn.commit()
    
    def query_raw(self, query: str, params: tuple = None, one: bool = False) -> Optional[List[Dict]]:
        """Execute a query and return results as list of dicts"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            if one:
                row = cursor.fetchone()
                return dict(row) if row else None
            rows = cursor.fetchall()
            return [dict(row) for row in rows] if rows else []
    
    def insert_raw(self, query: str, params: tuple = None) -> int:
        """Execute an insert query and return the last row ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            conn.commit()
            return cursor.lastrowid
    
    # ==================== User Settings Methods ====================
    
    def get_user_settings(self, user_id: int) -> Optional[Dict]:
        """Get user settings by user ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def save_user_settings(self, user_id: int, settings: Dict) -> int:
        """Save or update user settings"""
        existing = self.get_user_settings(user_id)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
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
                        update_fields.append(f"{field} = ?")
                        values.append(settings[field])
                
                if update_fields:
                    update_fields.append("updated_at = ?")
                    values.append(datetime.now().isoformat())
                    values.append(user_id)
                    
                    cursor.execute(f"""
                        UPDATE user_settings 
                        SET {', '.join(update_fields)}
                        WHERE user_id = ?
                    """, tuple(values))
                    conn.commit()
                    return existing['id']
            else:
                # Insert new settings
                cursor.execute("""
                    INSERT INTO user_settings (
                        user_id, ai_provider,
                        azure_openai_endpoint, azure_openai_api_key,
                        azure_openai_deployment_name, azure_openai_api_version,
                        gemini_api_key, gemini_model,
                        sender_email, sender_password,
                        email_host, email_port, imap_host, imap_port,
                        check_interval
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                conn.commit()
                return cursor.lastrowid
    
    def delete_user_settings(self, user_id: int):
        """Delete user settings"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
            conn.commit()

    # ==================== Chat Session Methods ====================
    
    def create_chat_session(self, user_id: int, title: str = "New Chat") -> int:
        """Create a new chat session"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_sessions (user_id, title)
                VALUES (?, ?)
            """, (user_id, title))
            conn.commit()
            return cursor.lastrowid
    
    def get_chat_sessions(self, user_id: int) -> List[Dict]:
        """Get all chat sessions for a user"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT cs.*, 
                       (SELECT COUNT(*) FROM chat_messages WHERE session_id = cs.id) as message_count,
                       (SELECT content FROM chat_messages WHERE session_id = cs.id ORDER BY created_at DESC LIMIT 1) as last_message
                FROM chat_sessions cs
                WHERE cs.user_id = ? AND cs.is_active = TRUE
                ORDER BY cs.updated_at DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_chat_session(self, session_id: int, user_id: int) -> Optional[Dict]:
        """Get a specific chat session"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM chat_sessions 
                WHERE id = ? AND user_id = ?
            """, (session_id, user_id))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_chat_session(self, session_id: int, user_id: int, title: str = None):
        """Update chat session title"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if title:
                cursor.execute("""
                    UPDATE chat_sessions 
                    SET title = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                """, (title, datetime.now().isoformat(), session_id, user_id))
            else:
                cursor.execute("""
                    UPDATE chat_sessions 
                    SET updated_at = ?
                    WHERE id = ? AND user_id = ?
                """, (datetime.now().isoformat(), session_id, user_id))
            conn.commit()
    
    def delete_chat_session(self, session_id: int, user_id: int) -> bool:
        """Delete a chat session (soft delete)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE chat_sessions 
                SET is_active = FALSE, updated_at = ?
                WHERE id = ? AND user_id = ?
            """, (datetime.now().isoformat(), session_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_chat_session_permanent(self, session_id: int, user_id: int) -> bool:
        """Permanently delete a chat session and all its messages"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Delete messages first
            cursor.execute("DELETE FROM chat_messages WHERE session_id = ? AND user_id = ?", 
                          (session_id, user_id))
            # Then delete session
            cursor.execute("DELETE FROM chat_sessions WHERE id = ? AND user_id = ?", 
                          (session_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    # ==================== Chat Message Methods ====================
    
    def save_chat_message(self, session_id: int, user_id: int, role: str, content: str,
                          has_chart: bool = False, chart_type: str = None, 
                          chart_data: Dict = None, has_export: bool = False) -> int:
        """Save a chat message"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_messages 
                (session_id, user_id, role, content, has_chart, chart_type, chart_data, has_export)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (session_id, user_id, role, content, has_chart, chart_type, 
                  json.dumps(chart_data) if chart_data else None, has_export))
            
            # Update session updated_at
            cursor.execute("""
                UPDATE chat_sessions SET updated_at = ? WHERE id = ?
            """, (datetime.now().isoformat(), session_id))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_chat_messages(self, session_id: int, user_id: int, limit: int = 100) -> List[Dict]:
        """Get all messages in a chat session"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM chat_messages 
                WHERE session_id = ? AND user_id = ?
                ORDER BY created_at ASC
                LIMIT ?
            """, (session_id, user_id, limit))
            messages = []
            for row in cursor.fetchall():
                msg = dict(row)
                if msg.get('chart_data'):
                    try:
                        msg['chart_data'] = json.loads(msg['chart_data'])
                    except:
                        pass
                messages.append(msg)
            return messages
    
    def get_session_messages(self, session_id: int, limit: int = 50) -> List[Dict]:
        """Get all messages in a session (simplified version for context)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT role, content, created_at FROM chat_messages 
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT ?
            """, (session_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_or_create_active_session(self, user_id: int) -> int:
        """Get the most recent active session or create a new one"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get most recent active session
            cursor.execute("""
                SELECT id FROM chat_sessions 
                WHERE user_id = ? AND is_active = TRUE
                ORDER BY updated_at DESC
                LIMIT 1
            """, (user_id,))
            row = cursor.fetchone()
            
            if row:
                return row['id']
            else:
                # Create new session
                return self.create_chat_session(user_id, "New Chat")
    
    def generate_session_title(self, session_id: int, user_id: int) -> str:
        """Generate a title based on the first user message"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT content FROM chat_messages 
                WHERE session_id = ? AND user_id = ? AND role = 'user'
                ORDER BY created_at ASC
                LIMIT 1
            """, (session_id, user_id))
            row = cursor.fetchone()
            
            if row:
                content = row['content']
                # Truncate to first 50 chars
                title = content[:50] + ('...' if len(content) > 50 else '')
                
                # Update session title
                cursor.execute("""
                    UPDATE chat_sessions SET title = ? WHERE id = ?
                """, (title, session_id))
                conn.commit()
                return title
            return "New Chat"

