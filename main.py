"""
Email AI Agent - Main Application
A complete AI Agent for automated email communication and response analysis
"""
import sys
import argparse
import logging
from typing import Optional

from services.email_service import EmailService
from services.ai_agent import AIAgent
from services.database import DatabaseService
from services.email_monitor import EmailMonitor, ManualResponseProcessor
from config.settings import SENDER_EMAIL

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EmailAgent:
    """Main Email AI Agent class"""
    
    def __init__(self):
        self.email_service = EmailService()
        self.ai_agent = AIAgent()
        self.database = DatabaseService()
        self.monitor = EmailMonitor(
            self.email_service,
            self.ai_agent,
            self.database,
            notification_callback=self._on_response_received
        )
        self.manual_processor = ManualResponseProcessor(
            self.email_service,
            self.ai_agent,
            self.database
        )
        
    def _on_response_received(self, email_record, response, analysis):
        """Callback when a response is received and processed"""
        print("\n" + "="*60)
        print("📬 RESPONSE RECEIVED AND ANALYZED!")
        print("="*60)
        print(f"From: {email_record['recipient_name']} ({email_record['recipient_email']})")
        print(f"Original Purpose: {email_record['purpose']}")
        print(f"\n📊 Analysis Results:")
        print(f"  Sentiment: {analysis.get('sentiment', 'unknown')}")
        print(f"  Decision: {analysis.get('decision', 'unknown')}")
        print(f"  Confidence: {analysis.get('confidence_score', 'N/A')}")
        print(f"\n📝 Summary: {analysis.get('summary', 'No summary available')}")
        print("="*60 + "\n")
    
    def send_email(
        self,
        sender_name: str,
        recipient_name: str,
        recipient_email: str,
        purpose: str,
        tone: str = "professional",
        additional_context: Optional[str] = None,
        notification_email: Optional[str] = None
    ) -> dict:
        """
        Send an AI-generated email to a recipient
        
        Args:
            sender_name: Name of the sender (Person A)
            recipient_name: Name of the recipient (Person B)
            recipient_email: Email of the recipient
            purpose: The purpose/request for the email
            tone: Tone of the email (professional, friendly, formal, casual)
            additional_context: Any additional context
            notification_email: Email to receive notifications (defaults to SENDER_EMAIL)
            
        Returns:
            Dictionary with email details and status
        """
        # Generate email using AI
        print(f"\n🤖 Generating email to {recipient_name}...")
        generated_email = self.ai_agent.generate_email(
            sender_name=sender_name,
            recipient_name=recipient_name,
            recipient_email=recipient_email,
            purpose=purpose,
            tone=tone,
            additional_context=additional_context
        )
        
        print(f"\n📧 Generated Email:")
        print(f"Subject: {generated_email['subject']}")
        print(f"Body:\n{generated_email['body']}")
        
        # Send the email
        print(f"\n📤 Sending email to {recipient_email}...")
        success = self.email_service.send_email(
            recipient_email=recipient_email,
            subject=generated_email['subject'],
            body=generated_email['body']
        )
        
        if success:
            # Save to database for tracking
            email_id = self.database.save_sent_email(
                sender_name=sender_name,
                sender_email=notification_email or SENDER_EMAIL,
                recipient_name=recipient_name,
                recipient_email=recipient_email,
                subject=generated_email['subject'],
                body=generated_email['body'],
                purpose=purpose
            )
            
            print(f"✅ Email sent successfully! (ID: {email_id})")
            print("📭 Waiting for response... The system will monitor for replies.")
            
            return {
                "success": True,
                "email_id": email_id,
                "subject": generated_email['subject'],
                "body": generated_email['body']
            }
        else:
            print("❌ Failed to send email")
            return {
                "success": False,
                "error": "Failed to send email"
            }
    
    def start_monitoring(self):
        """Start the email response monitoring service"""
        print("\n🔄 Starting email response monitoring...")
        print("Press Ctrl+C to stop\n")
        self.monitor.start()
        
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n⏹️ Stopping monitor...")
            self.monitor.stop()
            print("Monitor stopped.")
    
    def check_responses_once(self):
        """Check for responses once (without continuous monitoring)"""
        print("\n🔍 Checking for responses...")
        self.monitor.check_responses()
        print("✅ Check complete.")
    
    def process_manual_response(
        self,
        email_id: int,
        response_text: str
    ) -> dict:
        """
        Manually process a response (useful for testing)
        
        Args:
            email_id: ID of the original sent email
            response_text: The response text to analyze
            
        Returns:
            Analysis results
        """
        return self.manual_processor.process_response(
            sent_email_id=email_id,
            response_text=response_text
        )
    
    def list_emails(self):
        """List all tracked emails"""
        emails = self.database.get_all_emails()
        
        if not emails:
            print("\n📭 No emails tracked yet.")
            return
            
        print("\n📋 Tracked Emails:")
        print("-" * 80)
        
        for email in emails:
            status = "✅ Response received" if email['response_received'] else "⏳ Waiting for response"
            print(f"\nID: {email['id']}")
            print(f"To: {email['recipient_name']} ({email['recipient_email']})")
            print(f"Subject: {email['subject']}")
            print(f"Purpose: {email['purpose']}")
            print(f"Sent: {email['sent_at']}")
            print(f"Status: {status}")
            
            if email.get('analysis'):
                import json
                analysis = json.loads(email['analysis'])
                print(f"Response Summary: {analysis.get('summary', 'N/A')}")
                print(f"Decision: {analysis.get('decision', 'N/A')}")
            
            print("-" * 80)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Email AI Agent')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Send email command
    send_parser = subparsers.add_parser('send', help='Send an AI-generated email')
    send_parser.add_argument('--sender-name', '-s', required=True, help='Your name')
    send_parser.add_argument('--recipient-name', '-r', required=True, help='Recipient name')
    send_parser.add_argument('--recipient-email', '-e', required=True, help='Recipient email')
    send_parser.add_argument('--purpose', '-p', required=True, help='Purpose of the email')
    send_parser.add_argument('--tone', '-t', default='professional', 
                           choices=['professional', 'friendly', 'formal', 'casual'],
                           help='Tone of the email')
    send_parser.add_argument('--context', '-c', help='Additional context')
    send_parser.add_argument('--notify', '-n', help='Email to receive notifications')
    
    # Monitor command
    subparsers.add_parser('monitor', help='Start monitoring for responses')
    
    # Check command
    subparsers.add_parser('check', help='Check for responses once')
    
    # List command
    subparsers.add_parser('list', help='List all tracked emails')
    
    # Interactive command
    subparsers.add_parser('interactive', help='Start interactive mode')
    
    args = parser.parse_args()
    
    agent = EmailAgent()
    
    if args.command == 'send':
        agent.send_email(
            sender_name=args.sender_name,
            recipient_name=args.recipient_name,
            recipient_email=args.recipient_email,
            purpose=args.purpose,
            tone=args.tone,
            additional_context=args.context,
            notification_email=args.notify
        )
    elif args.command == 'monitor':
        agent.start_monitoring()
    elif args.command == 'check':
        agent.check_responses_once()
    elif args.command == 'list':
        agent.list_emails()
    elif args.command == 'interactive':
        interactive_mode(agent)
    else:
        parser.print_help()


def interactive_mode(agent: EmailAgent):
    """Interactive mode for the agent"""
    print("\n" + "="*60)
    print("🤖 EMAIL AI AGENT - INTERACTIVE MODE")
    print("="*60)
    
    while True:
        print("\n📬 What would you like to do?")
        print("1. Send a new email")
        print("2. Check for responses")
        print("3. Start continuous monitoring")
        print("4. List all emails")
        print("5. Process a manual response")
        print("6. Exit")
        
        choice = input("\nEnter your choice (1-6): ").strip()
        
        if choice == '1':
            print("\n--- Send New Email ---")
            sender_name = input("Your name: ").strip()
            recipient_name = input("Recipient's name: ").strip()
            recipient_email = input("Recipient's email: ").strip()
            purpose = input("What is the purpose of this email?\n> ").strip()
            
            print("\nTone options: professional, friendly, formal, casual")
            tone = input("Tone (default: professional): ").strip() or "professional"
            
            additional_context = input("Any additional context? (press Enter to skip)\n> ").strip() or None
            
            confirm = input(f"\nSend email to {recipient_name} ({recipient_email})? (y/n): ")
            if confirm.lower() == 'y':
                agent.send_email(
                    sender_name=sender_name,
                    recipient_name=recipient_name,
                    recipient_email=recipient_email,
                    purpose=purpose,
                    tone=tone,
                    additional_context=additional_context
                )
                
        elif choice == '2':
            agent.check_responses_once()
            
        elif choice == '3':
            agent.start_monitoring()
            
        elif choice == '4':
            agent.list_emails()
            
        elif choice == '5':
            print("\n--- Process Manual Response ---")
            email_id = int(input("Enter the email ID: ").strip())
            print("Enter the response text (end with a blank line):")
            lines = []
            while True:
                line = input()
                if line == '':
                    break
                lines.append(line)
            response_text = '\n'.join(lines)
            
            result = agent.process_manual_response(email_id, response_text)
            print(f"\n📊 Analysis: {result['analysis']}")
            print(f"📧 Notification sent: {result['notification_sent']}")
            
        elif choice == '6':
            print("\n👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
