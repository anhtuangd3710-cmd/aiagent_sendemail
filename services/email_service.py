"""
Email Service - Handles sending and receiving emails
"""
import smtplib
import imaplib
import email
import socket
import os
import mimetypes
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.application import MIMEApplication
from email import encoders
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
        self.sender_email = SENDER_EMAIL or ""
        self.sender_password = SENDER_PASSWORD or ""
        self._imap_available = None  # Cache IMAP availability
        
    def send_email(
        self, 
        recipient_email: str, 
        subject: str, 
        body: str,
        is_html: bool = False,
        attachments: List[Dict] = None
    ) -> bool:
        """
        Send an email to the recipient with optional attachments
        
        Args:
            recipient_email: Email address of recipient (Person B)
            subject: Email subject
            body: Email body content
            is_html: Whether the body is HTML formatted
            attachments: List of attachment dicts with 'filename', 'content' (bytes), 'content_type'
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Create message
            message = MIMEMultipart("mixed")
            message["Subject"] = subject
            message["From"] = self.sender_email
            message["To"] = recipient_email
            
            # Create the body part
            body_part = MIMEMultipart("alternative")
            content_type = "html" if is_html else "plain"
            body_part.attach(MIMEText(body, content_type))
            message.attach(body_part)
            
            # Add attachments if provided
            if attachments:
                for attachment in attachments:
                    self._add_attachment(message, attachment)
            
            # Connect and send
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.sendmail(
                    self.sender_email, 
                    recipient_email, 
                    message.as_string()
                )
                
            attachment_count = len(attachments) if attachments else 0
            logger.info(f"Email sent successfully to {recipient_email} with {attachment_count} attachment(s)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return False
    
    def _add_attachment(self, message: MIMEMultipart, attachment: Dict):
        """Add an attachment to the email message"""
        try:
            filename = attachment.get('filename', 'attachment')
            content = attachment.get('content')  # bytes
            content_type = attachment.get('content_type', 'application/octet-stream')
            
            if content is None:
                logger.warning(f"Attachment {filename} has no content, skipping")
                return
            
            # Determine the main and sub type
            maintype, subtype = content_type.split('/', 1) if '/' in content_type else ('application', 'octet-stream')
            
            if maintype == 'text':
                # Text files
                att = MIMEText(content.decode('utf-8', errors='ignore'), _subtype=subtype)
            elif maintype == 'application':
                att = MIMEApplication(content, _subtype=subtype)
            else:
                # Generic binary
                att = MIMEBase(maintype, subtype)
                att.set_payload(content)
                encoders.encode_base64(att)
            
            # Add header with filename
            att.add_header(
                'Content-Disposition',
                'attachment',
                filename=filename
            )
            
            message.attach(att)
            logger.info(f"Attached file: {filename} ({content_type})")
            
        except Exception as e:
            logger.error(f"Failed to add attachment: {str(e)}")
    
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
        # Check if credentials are configured
        if not self.sender_email or not self.sender_password:
            self._imap_available = False
            return {
                "success": False,
                "message": "Email not configured",
                "details": "Vui lòng cấu hình Email và App Password trong phần Profile/Cài đặt."
            }
        
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
    
    def check_imap_connection_with_config(self, imap_host: str = None, imap_port: int = None) -> Dict:
        """
        Test IMAP connection with custom host/port
        
        Args:
            imap_host: Custom IMAP host (default: use global config)
            imap_port: Custom IMAP port (default: use global config)
            
        Returns:
            Dict with 'success', 'message', and 'details'
        """
        host = imap_host or IMAP_HOST
        port = imap_port or IMAP_PORT
        
        # Check if credentials are configured
        if not self.sender_email or not self.sender_password:
            self._imap_available = False
            return {
                "success": False,
                "message": "Email not configured",
                "details": "Vui lòng cấu hình Email và App Password trong phần Profile/Cài đặt."
            }
        
        try:
            logger.info(f"Testing IMAP connection to {host}:{port} with {self.sender_email}...")
            mail = imaplib.IMAP4_SSL(host, port, timeout=15)
            mail.login(self.sender_email, self.sender_password)
            mail.select("INBOX")
            
            # Get mailbox status
            status, data = mail.status("INBOX", "(MESSAGES UNSEEN)")
            mail.logout()
            
            self._imap_available = True
            return {
                "success": True,
                "message": "IMAP connection successful",
                "details": f"Kết nối thành công đến {host}. " + (data[0].decode() if data else "")
            }
        except socket.timeout:
            self._imap_available = False
            return {
                "success": False,
                "message": "Connection timed out",
                "details": f"Không thể kết nối đến {host}:{port}. Vui lòng kiểm tra firewall/antivirus."
            }
        except imaplib.IMAP4.error as e:
            self._imap_available = False
            error_msg = str(e)
            if "AUTHENTICATIONFAILED" in error_msg.upper() or "invalid" in error_msg.lower():
                return {
                    "success": False,
                    "message": "Authentication failed",
                    "details": "Sai email hoặc App Password. Hãy kiểm tra lại và đảm bảo đã bật IMAP trong cài đặt Gmail."
                }
            return {
                "success": False,
                "message": "IMAP Error",
                "details": f"Lỗi: {error_msg}"
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
