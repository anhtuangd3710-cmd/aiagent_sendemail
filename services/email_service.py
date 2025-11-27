"""
Email Service - Handles sending and receiving emails
"""
import smtplib
import imaplib
import email
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from typing import Optional, List, Dict
import logging
from datetime import datetime

from config.settings import (
    EMAIL_HOST, EMAIL_PORT, IMAP_HOST, IMAP_PORT,
    SENDER_EMAIL, SENDER_PASSWORD
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set default timeout for socket connections
socket.setdefaulttimeout(30)


class EmailService:
    """Service for sending and receiving emails"""
    
    def __init__(self):
        self.sender_email = SENDER_EMAIL
        self.sender_password = SENDER_PASSWORD
        self._imap_available = None  # Cache IMAP availability
        
    def send_email(
        self, 
        recipient_email: str, 
        subject: str, 
        body: str,
        is_html: bool = False
    ) -> bool:
        """
        Send an email to the recipient
        
        Args:
            recipient_email: Email address of recipient (Person B)
            subject: Email subject
            body: Email body content
            is_html: Whether the body is HTML formatted
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.sender_email
            message["To"] = recipient_email
            
            # Attach body
            content_type = "html" if is_html else "plain"
            message.attach(MIMEText(body, content_type))
            
            # Connect and send
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.sendmail(
                    self.sender_email, 
                    recipient_email, 
                    message.as_string()
                )
                
            logger.info(f"Email sent successfully to {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return False
    
    def get_responses(
        self, 
        from_email: str, 
        subject_contains: Optional[str] = None,
        since_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Check for email responses from a specific sender
        
        Args:
            from_email: Email address to check responses from (Person B)
            subject_contains: Optional subject filter
            since_date: Only get emails after this date
            
        Returns:
            List of email dictionaries with subject, body, date
        """
        responses = []
        
        try:
            # Connect to IMAP server with timeout
            logger.info(f"Connecting to IMAP server {IMAP_HOST}:{IMAP_PORT}...")
            mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=30)
            logger.info("IMAP connection established, logging in...")
            mail.login(self.sender_email, self.sender_password)
            mail.select("INBOX")
            
            # Build search criteria
            search_criteria = f'FROM "{from_email}"'
            if since_date:
                date_str = since_date.strftime("%d-%b-%Y")
                search_criteria = f'({search_criteria} SINCE {date_str})'
            
            # Search for emails
            status, messages = mail.search(None, search_criteria)
            
            if status != "OK":
                logger.warning("No messages found")
                return responses
            
            email_ids = messages[0].split()
            
            for email_id in email_ids:
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                
                if status != "OK":
                    continue
                    
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Decode subject
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or "utf-8")
                        
                        # Filter by subject if specified
                        if subject_contains and subject_contains.lower() not in subject.lower():
                            continue
                        
                        # Get email body
                        body = self._get_email_body(msg)
                        
                        # Get date
                        date_str = msg["Date"]
                        
                        responses.append({
                            "email_id": email_id.decode(),
                            "from": from_email,
                            "subject": subject,
                            "body": body,
                            "date": date_str,
                            "message_id": msg.get("Message-ID", "")
                        })
            
            mail.logout()
            
        except socket.timeout:
            logger.error("IMAP connection timed out. Please check your network or firewall settings.")
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP authentication failed: {str(e)}. Please enable IMAP in Gmail settings.")
        except ConnectionRefusedError:
            logger.error("IMAP connection refused. Please check if IMAP is enabled in Gmail.")
        except Exception as e:
            logger.error(f"Failed to get responses: {str(e)}")
            
        return responses
    
    def check_imap_connection(self) -> Dict:
        """
        Test IMAP connection and return status
        
        Returns:
            Dict with 'success', 'message', and 'details'
        """
        try:
            logger.info(f"Testing IMAP connection to {IMAP_HOST}:{IMAP_PORT}...")
            mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=15)
            mail.login(self.sender_email, self.sender_password)
            mail.select("INBOX")
            
            # Get mailbox status
            status, data = mail.status("INBOX", "(MESSAGES UNSEEN)")
            mail.logout()
            
            self._imap_available = True
            return {
                "success": True,
                "message": "IMAP connection successful",
                "details": data[0].decode() if data else "Connected"
            }
        except socket.timeout:
            self._imap_available = False
            return {
                "success": False,
                "message": "Connection timed out",
                "details": "Không thể kết nối đến IMAP server. Vui lòng kiểm tra firewall/antivirus."
            }
        except imaplib.IMAP4.error as e:
            self._imap_available = False
            return {
                "success": False,
                "message": "Authentication failed",
                "details": f"Lỗi xác thực: {str(e)}. Hãy bật IMAP trong cài đặt Gmail."
            }
        except Exception as e:
            self._imap_available = False
            return {
                "success": False,
                "message": "Connection failed",
                "details": str(e)
            }
    
    def _get_email_body(self, msg) -> str:
        """Extract email body from message"""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        body = part.get_payload(decode=True).decode()
                    except:
                        body = part.get_payload()
                    break
        else:
            try:
                body = msg.get_payload(decode=True).decode()
            except:
                body = msg.get_payload()
                
        return body
    
    def mark_as_read(self, email_id: str) -> bool:
        """Mark an email as read"""
        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            mail.login(self.sender_email, self.sender_password)
            mail.select("INBOX")
            mail.store(email_id.encode(), '+FLAGS', '\\Seen')
            mail.logout()
            return True
        except Exception as e:
            logger.error(f"Failed to mark email as read: {str(e)}")
            return False
