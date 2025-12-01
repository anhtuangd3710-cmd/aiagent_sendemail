"""
Email Monitor Service - Monitors for responses and triggers analysis
With Auto-Reply support for automated response handling
"""
import time
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional, List, Dict
import logging

from services.email_service import EmailService
from services.ai_agent import AIAgent
from services.database import DatabaseService
from config.settings import CHECK_INTERVAL, SENDER_EMAIL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_datetime(value) -> datetime:
    """Parse datetime from various formats (string or datetime object)"""
    if value is None:
        return datetime.now()
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Try different formats
        for fmt in [
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d"
        ]:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        # Try fromisoformat as last resort
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except:
            pass
    # Default to now if all parsing fails
    logger.warning(f"Could not parse datetime: {value}, using current time")
    return datetime.now()


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
    
    def check_responses_with_details(self) -> Dict:
        """Check for responses and return detailed results"""
        results = {
            "pending_emails": 0,
            "responses_found": 0,
            "responses_processed": 0,
            "errors": [],
            "details": []
        }
        
        pending_emails = self.database.get_pending_emails()
        
        if not pending_emails:
            logger.info("No pending emails to check")
            return results
        
        results["pending_emails"] = len(pending_emails)
        logger.info(f"Checking responses for {len(pending_emails)} pending emails using {self.email_service.sender_email}")
        
        for email_record in pending_emails:
            try:
                response_info = self._process_email_responses_with_details(email_record)
                if response_info:
                    results["responses_found"] += response_info.get("found", 0)
                    results["responses_processed"] += response_info.get("processed", 0)
                    results["details"].append(response_info)
            except Exception as e:
                error_msg = f"Error for email {email_record['id']} to {email_record['recipient_email']}: {str(e)}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
        
        return results
    
    def _process_email_responses_with_details(self, email_record: dict) -> Dict:
        """Process responses for a specific sent email and return details"""
        recipient_email = email_record['recipient_email']
        sent_date = parse_datetime(email_record['sent_at'])
        
        result = {
            "email_id": email_record['id'],
            "recipient": recipient_email,
            "found": 0,
            "processed": 0,
            "responses": []
        }
        
        try:
            # Get responses using instance's email service (with user's IMAP settings)
            responses = self.email_service.get_responses_with_config(
                from_email=recipient_email,
                subject_contains=email_record['subject'].split()[:3][0] if email_record['subject'] else None,
                since_date=sent_date - timedelta(hours=1)
            )
            
            if not responses:
                logger.info(f"No responses found from {recipient_email}")
                return result
            
            result["found"] = len(responses)
            logger.info(f"Found {len(responses)} potential responses from {recipient_email}")
            
            # Process each response
            for response in responses:
                try:
                    analysis = self._analyze_and_notify(email_record, response)
                    result["processed"] += 1
                    result["responses"].append({
                        "subject": response.get('subject', ''),
                        "analyzed": True,
                        "decision": analysis.get('decision', 'unknown') if analysis else 'unknown'
                    })
                except Exception as e:
                    logger.error(f"Failed to process response: {str(e)}")
                    result["responses"].append({
                        "subject": response.get('subject', ''),
                        "analyzed": False,
                        "error": str(e)
                    })
        except Exception as e:
            logger.error(f"Failed to get responses from {recipient_email}: {str(e)}")
            result["error"] = str(e)
        
        return result

    def _process_email_responses(self, email_record: dict):
        """Process responses for a specific sent email"""
        recipient_email = email_record['recipient_email']
        sent_date = parse_datetime(email_record['sent_at'])
        
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
        
        # Store response_id in response dict for auto-reply
        response['response_id'] = response_id
        
        # Try to create auto-reply draft if enabled
        self._try_create_auto_reply(email_record, response, analysis)
        
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
    
    def _try_create_auto_reply(self, email_record: dict, response: dict, analysis: dict):
        """Try to create auto-reply draft if enabled for user"""
        try:
            user_id = email_record.get('user_id')
            if not user_id:
                logger.debug("No user_id in email_record, skipping auto-reply")
                return
            
            # Lazy import to avoid circular imports
            from services.auto_reply_service import AutoReplyService
            
            auto_reply_service = AutoReplyService(
                self.database, 
                self.ai_agent, 
                self.email_service
            )
            
            # Check if auto-reply is enabled for this user
            settings = auto_reply_service.get_user_settings(user_id)
            if not settings or not settings.get('enabled', False):
                logger.debug(f"Auto-reply disabled for user {user_id}")
                return
            
            # Prepare incoming email data
            incoming_email = {
                'response_id': response.get('response_id'),
                'from_email': email_record['recipient_email'],
                'from_name': email_record['recipient_name'],
                'subject': response.get('subject', ''),
                'body': response.get('body', '')
            }
            
            # Create auto-reply draft
            draft = auto_reply_service.analyze_and_create_draft(
                user_id=user_id,
                original_email=email_record,
                incoming_email=incoming_email,
                conversation_history=None  # Could fetch from DB if needed
            )
            
            if draft:
                logger.info(f"Auto-reply draft created for user {user_id}, draft_id: {draft.get('id')}")
            else:
                logger.debug(f"No auto-reply draft created (AI decided not to reply)")
                
        except Exception as e:
            logger.error(f"Error creating auto-reply draft: {e}")
            # Don't raise - auto-reply is optional feature


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
