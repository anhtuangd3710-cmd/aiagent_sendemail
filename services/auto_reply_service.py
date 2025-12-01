"""
Auto Reply Service - AI-powered automatic email reply with user confirmation
Tự động phân tích email phản hồi, soạn draft và gửi xác nhận cho user
"""
import secrets
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AutoReplyService:
    """Service for managing auto-reply drafts and confirmations"""
    
    def __init__(self, database, ai_agent, email_service):
        self.database = database
        self.ai_agent = ai_agent
        self.email_service = email_service
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Ensure auto_reply tables exist"""
        try:
            # Check if table exists
            result = self.database.query_raw("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'auto_reply_drafts'
                )
            """, one=True)
            
            if not result or not result.get('exists', False):
                self._create_tables()
        except Exception as e:
            logger.warning(f"Table check failed, creating tables: {e}")
            self._create_tables()
    
    def _create_tables(self):
        """Create auto-reply related tables"""
        try:
            # Auto reply drafts table
            self.database.execute_raw("""
                CREATE TABLE IF NOT EXISTS auto_reply_drafts (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    original_email_id INTEGER REFERENCES sent_emails(id),
                    incoming_response_id INTEGER REFERENCES responses(id),
                    
                    -- Incoming email info
                    from_email VARCHAR(255) NOT NULL,
                    from_name VARCHAR(255),
                    incoming_subject TEXT,
                    incoming_body TEXT,
                    
                    -- AI generated draft
                    draft_subject TEXT NOT NULL,
                    draft_body TEXT NOT NULL,
                    ai_reasoning TEXT,
                    should_reply BOOLEAN DEFAULT TRUE,
                    confidence_score DECIMAL(3,2),
                    
                    -- Confirmation
                    confirmation_token VARCHAR(128) UNIQUE,
                    token_expires_at TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'pending',
                    
                    -- Timestamps
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    confirmed_at TIMESTAMP,
                    sent_at TIMESTAMP,
                    rejected_at TIMESTAMP
                )
            """)
            
            # Auto reply settings per user
            self.database.execute_raw("""
                CREATE TABLE IF NOT EXISTS auto_reply_settings (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    enabled BOOLEAN DEFAULT FALSE,
                    auto_send_threshold DECIMAL(3,2) DEFAULT 0.9,
                    require_confirmation BOOLEAN DEFAULT TRUE,
                    confirmation_timeout_hours INTEGER DEFAULT 24,
                    reply_languages TEXT DEFAULT 'vi,en',
                    exclude_keywords TEXT,
                    only_business_hours BOOLEAN DEFAULT FALSE,
                    business_hours_start INTEGER DEFAULT 9,
                    business_hours_end INTEGER DEFAULT 18,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Indexes
            self.database.execute_raw("""
                CREATE INDEX IF NOT EXISTS idx_auto_reply_drafts_user ON auto_reply_drafts(user_id)
            """)
            self.database.execute_raw("""
                CREATE INDEX IF NOT EXISTS idx_auto_reply_drafts_token ON auto_reply_drafts(confirmation_token)
            """)
            self.database.execute_raw("""
                CREATE INDEX IF NOT EXISTS idx_auto_reply_drafts_status ON auto_reply_drafts(status)
            """)
            
            logger.info("Auto-reply tables created successfully")
        except Exception as e:
            logger.error(f"Error creating auto-reply tables: {e}")
            raise
    
    def analyze_and_create_draft(
        self,
        user_id: int,
        original_email: Dict,
        incoming_email: Dict,
        conversation_history: List[Dict] = None
    ) -> Optional[Dict]:
        """
        Analyze incoming email and create auto-reply draft
        
        Args:
            user_id: User ID
            original_email: The original sent email record
            incoming_email: The incoming response email
            conversation_history: Previous emails in this thread
            
        Returns:
            Draft record or None if should not reply
        """
        try:
            # Get user settings
            settings = self.get_user_settings(user_id)
            if not settings or not settings.get('enabled', False):
                logger.info(f"Auto-reply disabled for user {user_id}")
                return None
            
            # Build conversation context
            context = self._build_conversation_context(
                original_email, 
                incoming_email, 
                conversation_history
            )
            
            # Ask AI to analyze and generate draft
            ai_response = self._ai_analyze_and_draft(context, settings)
            
            if not ai_response:
                logger.warning("AI did not return a valid response")
                return None
            
            # Check if AI recommends replying
            if not ai_response.get('should_reply', False):
                logger.info(f"AI recommends not replying: {ai_response.get('reasoning')}")
                return None
            
            # Generate confirmation token
            token = secrets.token_urlsafe(64)
            token_expires = datetime.now() + timedelta(
                hours=settings.get('confirmation_timeout_hours', 24)
            )
            
            # Save draft to database
            draft_id = self._save_draft(
                user_id=user_id,
                original_email_id=original_email.get('id'),
                incoming_response_id=incoming_email.get('response_id'),
                from_email=incoming_email.get('from_email', incoming_email.get('from', '')),
                from_name=incoming_email.get('from_name', ''),
                incoming_subject=incoming_email.get('subject', ''),
                incoming_body=incoming_email.get('body', ''),
                draft_subject=ai_response.get('subject', ''),
                draft_body=ai_response.get('body', ''),
                ai_reasoning=ai_response.get('reasoning', ''),
                should_reply=ai_response.get('should_reply', True),
                confidence_score=ai_response.get('confidence', 0.8),
                confirmation_token=token,
                token_expires_at=token_expires
            )
            
            # Get the full draft record
            draft = self.get_draft_by_id(draft_id)
            
            # Send confirmation email to user if required
            if settings.get('require_confirmation', True):
                self._send_confirmation_email(user_id, draft, original_email)
            elif ai_response.get('confidence', 0) >= settings.get('auto_send_threshold', 0.9):
                # Auto-send if confidence is high enough
                self.confirm_and_send(token)
            
            return draft
            
        except Exception as e:
            logger.error(f"Error creating auto-reply draft: {e}")
            return None
    
    def _build_conversation_context(
        self,
        original_email: Dict,
        incoming_email: Dict,
        conversation_history: List[Dict] = None
    ) -> str:
        """Build conversation context for AI"""
        context = f"""
=== CUỘC HỘI THOẠI EMAIL ===

1. EMAIL GỐC ĐÃ GỬI:
- Người gửi: {original_email.get('sender_name')} <{original_email.get('sender_email')}>
- Người nhận: {original_email.get('recipient_name')} <{original_email.get('recipient_email')}>
- Tiêu đề: {original_email.get('subject')}
- Mục đích: {original_email.get('purpose', 'Không rõ')}
- Nội dung:
{original_email.get('body', '')}

---

2. EMAIL PHẢN HỒI NHẬN ĐƯỢC:
- Từ: {incoming_email.get('from_name', '')} <{incoming_email.get('from_email', incoming_email.get('from', ''))}>
- Tiêu đề: {incoming_email.get('subject', '')}
- Nội dung:
{incoming_email.get('body', '')}
"""
        
        if conversation_history:
            context += "\n\n3. LỊCH SỬ HỘI THOẠI TRƯỚC:\n"
            for i, email in enumerate(conversation_history[-5:], 1):  # Last 5 emails
                context += f"""
[{i}] {email.get('direction', 'sent')}: {email.get('subject', '')}
{email.get('body', '')[:500]}...
---
"""
        
        return context
    
    def _ai_analyze_and_draft(self, context: str, settings: Dict) -> Optional[Dict]:
        """Use AI to analyze and create draft reply"""
        prompt = f"""
Bạn là trợ lý AI chuyên nghiệp giúp phân tích và soạn email phản hồi tự động.

{context}

=== YÊU CẦU ===
1. Phân tích email phản hồi và quyết định có nên trả lời hay không
2. Nếu nên trả lời, soạn email phản hồi phù hợp
3. Email phản hồi phải:
   - Chuyên nghiệp, lịch sự
   - Phù hợp với ngữ cảnh cuộc hội thoại
   - Trả lời đúng câu hỏi/vấn đề được nêu
   - Ngắn gọn, súc tích

=== QUY TẮC ===
- KHÔNG trả lời nếu: email spam, quảng cáo, email tự động, hoặc không cần phản hồi
- NÊN trả lời nếu: có câu hỏi cụ thể, cần xác nhận, yêu cầu thông tin, v.v.

Trả về JSON với format:
{{
    "should_reply": true/false,
    "reasoning": "Lý do tại sao nên/không nên trả lời",
    "confidence": 0.0-1.0,
    "subject": "Re: Tiêu đề email",
    "body": "Nội dung email phản hồi (nếu should_reply = true)"
}}
"""
        
        try:
            response = self.ai_agent.model.generate_content(prompt)
            result = self.ai_agent._extract_json(response.text)
            return result
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            return None
    
    def _save_draft(self, **kwargs) -> int:
        """Save draft to database"""
        query = """
            INSERT INTO auto_reply_drafts (
                user_id, original_email_id, incoming_response_id,
                from_email, from_name, incoming_subject, incoming_body,
                draft_subject, draft_body, ai_reasoning,
                should_reply, confidence_score,
                confirmation_token, token_expires_at, status
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending'
            ) RETURNING id
        """
        return self.database.insert_raw(query, (
            kwargs.get('user_id'),
            kwargs.get('original_email_id'),
            kwargs.get('incoming_response_id'),
            kwargs.get('from_email'),
            kwargs.get('from_name'),
            kwargs.get('incoming_subject'),
            kwargs.get('incoming_body'),
            kwargs.get('draft_subject'),
            kwargs.get('draft_body'),
            kwargs.get('ai_reasoning'),
            kwargs.get('should_reply'),
            kwargs.get('confidence_score'),
            kwargs.get('confirmation_token'),
            kwargs.get('token_expires_at')
        ))
    
    def get_draft_by_id(self, draft_id: int) -> Optional[Dict]:
        """Get draft by ID"""
        return self.database.query_raw(
            "SELECT * FROM auto_reply_drafts WHERE id = %s",
            (draft_id,),
            one=True
        )
    
    def get_draft_by_token(self, token: str) -> Optional[Dict]:
        """Get draft by confirmation token"""
        return self.database.query_raw(
            "SELECT * FROM auto_reply_drafts WHERE confirmation_token = %s",
            (token,),
            one=True
        )
    
    def get_pending_drafts(self, user_id: int) -> List[Dict]:
        """Get all pending drafts for a user"""
        return self.database.query_raw(
            """SELECT * FROM auto_reply_drafts 
               WHERE user_id = %s AND status = 'pending'
               ORDER BY created_at DESC""",
            (user_id,)
        )
    
    def confirm_and_send(self, token: str) -> Dict:
        """Confirm and send the auto-reply"""
        draft = self.get_draft_by_token(token)
        
        if not draft:
            return {"success": False, "error": "Token không hợp lệ hoặc đã hết hạn"}
        
        if draft['status'] != 'pending':
            return {"success": False, "error": f"Email đã được xử lý: {draft['status']}"}
        
        # Check token expiration
        if draft['token_expires_at'] and datetime.now() > draft['token_expires_at']:
            self._update_draft_status(draft['id'], 'expired')
            return {"success": False, "error": "Link xác nhận đã hết hạn"}
        
        # Send the reply email
        try:
            # Get user's email settings
            user_settings = self.database.get_user_settings(draft['user_id'])
            
            if user_settings and user_settings.get('sender_email'):
                sender_email = user_settings['sender_email']
                sender_password = user_settings.get('sender_password', '')
                
                # Create email service with user's credentials
                from services.email_service import EmailService
                user_email_service = EmailService(
                    sender_email=sender_email,
                    sender_password=sender_password,
                    email_host=user_settings.get('email_host', 'smtp.gmail.com'),
                    email_port=user_settings.get('email_port', 587)
                )
            else:
                user_email_service = self.email_service
            
            # Send the email
            success = user_email_service.send_email(
                recipient_email=draft['from_email'],
                subject=draft['draft_subject'],
                body=draft['draft_body']
            )
            
            if success:
                self._update_draft_status(draft['id'], 'sent')
                self.database.execute_raw(
                    "UPDATE auto_reply_drafts SET sent_at = %s WHERE id = %s",
                    (datetime.now(), draft['id'])
                )
                return {"success": True, "message": "Email đã được gửi thành công!"}
            else:
                return {"success": False, "error": "Không thể gửi email. Vui lòng thử lại."}
                
        except Exception as e:
            logger.error(f"Error sending auto-reply: {e}")
            return {"success": False, "error": str(e)}
    
    def reject_draft(self, token: str) -> Dict:
        """Reject the auto-reply draft"""
        draft = self.get_draft_by_token(token)
        
        if not draft:
            return {"success": False, "error": "Token không hợp lệ"}
        
        if draft['status'] != 'pending':
            return {"success": False, "error": f"Email đã được xử lý: {draft['status']}"}
        
        self._update_draft_status(draft['id'], 'rejected')
        self.database.execute_raw(
            "UPDATE auto_reply_drafts SET rejected_at = %s WHERE id = %s",
            (datetime.now(), draft['id'])
        )
        
        return {"success": True, "message": "Đã từ chối email tự động"}
    
    def _update_draft_status(self, draft_id: int, status: str):
        """Update draft status"""
        self.database.execute_raw(
            "UPDATE auto_reply_drafts SET status = %s WHERE id = %s",
            (status, draft_id)
        )
    
    def _send_confirmation_email(self, user_id: int, draft: Dict, original_email: Dict):
        """Send confirmation email to user"""
        # Get user info
        user = self.database.query_raw(
            "SELECT * FROM users WHERE id = %s",
            (user_id,),
            one=True
        )
        
        if not user:
            logger.error(f"User {user_id} not found")
            return
        
        # Build confirmation URL
        base_url = os.environ.get('APP_BASE_URL', 'https://your-app.vercel.app')
        confirm_url = f"{base_url}/api/auto-reply/confirm/{draft['confirmation_token']}"
        reject_url = f"{base_url}/api/auto-reply/reject/{draft['confirmation_token']}"
        
        # Generate HTML email
        html_body = self._generate_confirmation_email_html(
            user=user,
            draft=draft,
            original_email=original_email,
            confirm_url=confirm_url,
            reject_url=reject_url
        )
        
        # Send email
        try:
            self.email_service.send_email(
                recipient_email=user['email'],
                subject=f"🤖 Xác nhận gửi email tự động - {draft['draft_subject']}",
                body=html_body,
                is_html=True
            )
            logger.info(f"Confirmation email sent to {user['email']}")
        except Exception as e:
            logger.error(f"Failed to send confirmation email: {e}")
    
    def _generate_confirmation_email_html(
        self,
        user: Dict,
        draft: Dict,
        original_email: Dict,
        confirm_url: str,
        reject_url: str
    ) -> str:
        """Generate HTML for confirmation email"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; background-color: #f5f7fb;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); border-radius: 16px 16px 0 0; padding: 30px; text-align: center;">
            <div style="width: 60px; height: 60px; background: rgba(255,255,255,0.2); border-radius: 50%; margin: 0 auto 15px; line-height: 60px;">
                <span style="font-size: 28px;">🤖</span>
            </div>
            <h1 style="color: white; margin: 0; font-size: 24px;">Email AI Agent</h1>
            <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0;">Xác nhận gửi email tự động</p>
        </div>
        
        <!-- Content -->
        <div style="background: white; padding: 30px; border-radius: 0 0 16px 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
            <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                Xin chào <strong>{user.get('full_name', user['username'])}</strong>,
            </p>
            
            <p style="color: #6b7280; font-size: 14px; line-height: 1.6;">
                AI đã phát hiện email phản hồi và soạn sẵn nội dung trả lời. Vui lòng xem xét và xác nhận:
            </p>
            
            <!-- Original Email Summary -->
            <div style="background: #f3f4f6; border-radius: 12px; padding: 20px; margin: 20px 0;">
                <h3 style="color: #374151; margin: 0 0 10px; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;">
                    📧 Email gốc đã gửi
                </h3>
                <p style="color: #6b7280; margin: 5px 0; font-size: 14px;">
                    <strong>Đến:</strong> {original_email.get('recipient_name')} &lt;{original_email.get('recipient_email')}&gt;
                </p>
                <p style="color: #6b7280; margin: 5px 0; font-size: 14px;">
                    <strong>Tiêu đề:</strong> {original_email.get('subject')}
                </p>
            </div>
            
            <!-- Incoming Email -->
            <div style="background: #fef3c7; border-radius: 12px; padding: 20px; margin: 20px 0;">
                <h3 style="color: #92400e; margin: 0 0 10px; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;">
                    📨 Email phản hồi nhận được
                </h3>
                <p style="color: #78350f; margin: 5px 0; font-size: 14px;">
                    <strong>Từ:</strong> {draft.get('from_name', '')} &lt;{draft['from_email']}&gt;
                </p>
                <p style="color: #78350f; margin: 5px 0; font-size: 14px;">
                    <strong>Tiêu đề:</strong> {draft.get('incoming_subject', '')}
                </p>
                <div style="background: rgba(255,255,255,0.5); border-radius: 8px; padding: 15px; margin-top: 10px; font-size: 14px; color: #78350f; white-space: pre-wrap;">
{draft.get('incoming_body', '')[:500]}{'...' if len(draft.get('incoming_body', '')) > 500 else ''}
                </div>
            </div>
            
            <!-- AI Draft -->
            <div style="background: #ecfdf5; border-left: 4px solid #10b981; border-radius: 0 12px 12px 0; padding: 20px; margin: 20px 0;">
                <h3 style="color: #047857; margin: 0 0 10px; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;">
                    ✨ Email trả lời do AI soạn
                </h3>
                <p style="color: #065f46; margin: 5px 0; font-size: 14px;">
                    <strong>Tiêu đề:</strong> {draft['draft_subject']}
                </p>
                <div style="background: rgba(255,255,255,0.7); border-radius: 8px; padding: 15px; margin-top: 10px; font-size: 14px; color: #065f46; white-space: pre-wrap;">
{draft['draft_body']}
                </div>
                <p style="color: #047857; margin: 15px 0 0; font-size: 12px;">
                    💡 <strong>Lý do AI:</strong> {draft.get('ai_reasoning', 'Dựa trên ngữ cảnh cuộc hội thoại')}
                </p>
            </div>
            
            <!-- Action Buttons -->
            <div style="text-align: center; margin: 30px 0;">
                <a href="{confirm_url}" style="display: inline-block; background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 10px; font-weight: 600; font-size: 16px; margin: 5px;">
                    ✅ Xác nhận gửi
                </a>
                <a href="{reject_url}" style="display: inline-block; background: #f3f4f6; color: #6b7280; padding: 14px 32px; text-decoration: none; border-radius: 10px; font-weight: 600; font-size: 16px; margin: 5px;">
                    ❌ Từ chối
                </a>
            </div>
            
            <p style="color: #9ca3af; font-size: 12px; text-align: center; margin-top: 20px;">
                ⏰ Link xác nhận sẽ hết hạn sau 24 giờ
            </p>
        </div>
        
        <!-- Footer -->
        <div style="text-align: center; padding: 20px; color: #9ca3af; font-size: 12px;">
            <p>Email này được gửi tự động bởi Email AI Agent</p>
            <p>© 2024 Email AI Agent. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""
    
    # ==================== User Settings ====================
    
    def get_user_settings(self, user_id: int) -> Optional[Dict]:
        """Get auto-reply settings for user"""
        return self.database.query_raw(
            "SELECT * FROM auto_reply_settings WHERE user_id = %s",
            (user_id,),
            one=True
        )
    
    def save_user_settings(self, user_id: int, settings: Dict) -> bool:
        """Save auto-reply settings for user"""
        existing = self.get_user_settings(user_id)
        
        try:
            if existing:
                self.database.execute_raw("""
                    UPDATE auto_reply_settings SET
                        enabled = %s,
                        auto_send_threshold = %s,
                        require_confirmation = %s,
                        confirmation_timeout_hours = %s,
                        reply_languages = %s,
                        exclude_keywords = %s,
                        only_business_hours = %s,
                        business_hours_start = %s,
                        business_hours_end = %s,
                        updated_at = %s
                    WHERE user_id = %s
                """, (
                    settings.get('enabled', False),
                    settings.get('auto_send_threshold', 0.9),
                    settings.get('require_confirmation', True),
                    settings.get('confirmation_timeout_hours', 24),
                    settings.get('reply_languages', 'vi,en'),
                    settings.get('exclude_keywords', ''),
                    settings.get('only_business_hours', False),
                    settings.get('business_hours_start', 9),
                    settings.get('business_hours_end', 18),
                    datetime.now(),
                    user_id
                ))
            else:
                self.database.execute_raw("""
                    INSERT INTO auto_reply_settings (
                        user_id, enabled, auto_send_threshold, require_confirmation,
                        confirmation_timeout_hours, reply_languages, exclude_keywords,
                        only_business_hours, business_hours_start, business_hours_end
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id,
                    settings.get('enabled', False),
                    settings.get('auto_send_threshold', 0.9),
                    settings.get('require_confirmation', True),
                    settings.get('confirmation_timeout_hours', 24),
                    settings.get('reply_languages', 'vi,en'),
                    settings.get('exclude_keywords', ''),
                    settings.get('only_business_hours', False),
                    settings.get('business_hours_start', 9),
                    settings.get('business_hours_end', 18)
                ))
            return True
        except Exception as e:
            logger.error(f"Error saving auto-reply settings: {e}")
            return False
    
    def get_all_drafts(self, user_id: int, status: str = None) -> List[Dict]:
        """Get all drafts for a user, optionally filtered by status"""
        if status:
            return self.database.query_raw(
                """SELECT * FROM auto_reply_drafts 
                   WHERE user_id = %s AND status = %s
                   ORDER BY created_at DESC""",
                (user_id, status)
            )
        return self.database.query_raw(
            """SELECT * FROM auto_reply_drafts 
               WHERE user_id = %s
               ORDER BY created_at DESC""",
            (user_id,)
        )


# Need to import os for environment variables
import os
