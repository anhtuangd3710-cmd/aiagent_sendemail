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
                LEFT JOIN responses r ON se.id = r.sent_email_id
                ORDER BY se.sent_at DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
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

