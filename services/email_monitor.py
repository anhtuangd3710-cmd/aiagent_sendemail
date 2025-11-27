"""
Email Monitor Service - Monitors for responses and triggers analysis
"""
import time
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional
import logging

from services.email_service import EmailService
from services.ai_agent import AIAgent
from services.database import DatabaseService
from config.settings import CHECK_INTERVAL, SENDER_EMAIL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmailMonitor:
    """Service that monitors for email responses and processes them"""
    
    def __init__(
        self,
        email_service: EmailService,
        ai_agent: AIAgent,
        database: DatabaseService,
        notification_callback: Optional[Callable] = None
    ):
        self.email_service = email_service
        self.ai_agent = ai_agent
        self.database = database
        self.notification_callback = notification_callback
        self._running = False
        self._thread = None
        
    def start(self):
        """Start the email monitoring service"""
        if self._running:
            logger.warning("Monitor is already running")
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Email monitor started")
        
    def stop(self):
        """Stop the email monitoring service"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Email monitor stopped")
        
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self._running:
            try:
                self.check_responses()
            except Exception as e:
                logger.error(f"Error in monitor loop: {str(e)}")
            
            time.sleep(CHECK_INTERVAL)
    
    def check_responses(self):
        """Check for responses to pending emails"""
        pending_emails = self.database.get_pending_emails()
        
        if not pending_emails:
            logger.debug("No pending emails to check")
            return
            
        logger.info(f"Checking responses for {len(pending_emails)} pending emails")
        
        for email_record in pending_emails:
            try:
                self._process_email_responses(email_record)
            except Exception as e:
                logger.error(f"Error processing responses for email {email_record['id']}: {str(e)}")
    
    def _process_email_responses(self, email_record: dict):
        """Process responses for a specific sent email"""
        recipient_email = email_record['recipient_email']
        sent_date = datetime.fromisoformat(email_record['sent_at'])
        
        # Get responses from the recipient
        responses = self.email_service.get_responses(
            from_email=recipient_email,
            subject_contains=email_record['subject'].split()[:3][0] if email_record['subject'] else None,
            since_date=sent_date - timedelta(hours=1)
        )
        
        if not responses:
            return
            
        logger.info(f"Found {len(responses)} potential responses from {recipient_email}")
        
        # Process each response
        for response in responses:
            self._analyze_and_notify(email_record, response)
    
    def _analyze_and_notify(self, email_record: dict, response: dict):
        """Analyze a response and send notification to person A"""
        logger.info(f"Analyzing response from {email_record['recipient_email']}")
        
        # Analyze the response using AI
        analysis = self.ai_agent.analyze_response(
            original_email_subject=email_record['subject'],
            original_email_body=email_record['body'],
            original_purpose=email_record['purpose'],
            response_body=response['body'],
            response_subject=response['subject']
        )
        
        # Save the response and analysis
        response_id = self.database.save_response(
            sent_email_id=email_record['id'],
            response_subject=response['subject'],
            response_body=response['body'],
            analysis=analysis
        )
        
        # Generate notification email
        notification = self.ai_agent.generate_notification_email(
            sender_name=email_record['sender_name'],
            original_purpose=email_record['purpose'],
            recipient_name=email_record['recipient_name'],
            analysis=analysis
        )
        
        # Send notification to person A
        notification_sent = self.email_service.send_email(
            recipient_email=email_record['sender_email'],
            subject=notification['subject'],
            body=notification['body']
        )
        
        if notification_sent:
            self.database.mark_notification_sent(response_id)
            logger.info(f"Notification sent to {email_record['sender_email']}")
            
            # Call notification callback if provided
            if self.notification_callback:
                self.notification_callback(email_record, response, analysis)
        else:
            logger.error("Failed to send notification email")
        
        return analysis


class ManualResponseProcessor:
    """Process responses manually without continuous monitoring"""
    
    def __init__(
        self,
        email_service: EmailService,
        ai_agent: AIAgent,
        database: DatabaseService
    ):
        self.email_service = email_service
        self.ai_agent = ai_agent
        self.database = database
        
    def process_response(
        self,
        sent_email_id: int,
        response_text: str,
        response_subject: str = "Re: Response"
    ) -> dict:
        """
        Manually process a response text (useful for testing or manual input)
        
        Args:
            sent_email_id: ID of the original sent email
            response_text: The response text to analyze
            response_subject: Subject of the response
            
        Returns:
            Analysis results and notification status
        """
        email_record = self.database.get_email_by_id(sent_email_id)
        
        if not email_record:
            raise ValueError(f"Email with ID {sent_email_id} not found")
        
        # Analyze the response
        analysis = self.ai_agent.analyze_response(
            original_email_subject=email_record['subject'],
            original_email_body=email_record['body'],
            original_purpose=email_record['purpose'],
            response_body=response_text,
            response_subject=response_subject
        )
        
        # Save response
        response_id = self.database.save_response(
            sent_email_id=sent_email_id,
            response_subject=response_subject,
            response_body=response_text,
            analysis=analysis
        )
        
        # Generate and send notification
        notification = self.ai_agent.generate_notification_email(
            sender_name=email_record['sender_name'],
            original_purpose=email_record['purpose'],
            recipient_name=email_record['recipient_name'],
            analysis=analysis
        )
        
        notification_sent = self.email_service.send_email(
            recipient_email=email_record['sender_email'],
            subject=notification['subject'],
            body=notification['body']
        )
        
        if notification_sent:
            self.database.mark_notification_sent(response_id)
        
        return {
            "analysis": analysis,
            "notification": notification,
            "notification_sent": notification_sent
        }
