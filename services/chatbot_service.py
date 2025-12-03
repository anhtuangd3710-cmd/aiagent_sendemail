"""
Chatbot Service - AI-powered chatbot for email analytics
Allows users to ask questions about their email data
Generates charts, statistics, and Excel exports
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import io
import base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatbotService:
    """Service for AI-powered chatbot with email analytics"""
    
    # Free tier limits
    FREE_DAILY_LIMIT = 10  # Free queries per day without API key
    
    def __init__(self, database, ai_agent):
        self.database = database
        self.ai_agent = ai_agent
    
    def _get_user_daily_usage(self, user_id: int) -> int:
        """Get user's chatbot usage count for today"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            result = self.database.query_raw(
                """SELECT COUNT(*) as count FROM chat_messages 
                   WHERE user_id = %s AND role = 'user' 
                   AND DATE(created_at) = %s""",
                (user_id, today)
            )
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.error(f"Error getting user daily usage: {e}")
            return 0
    
    def check_usage_limit(self, user_id: int, user_settings: Dict = None) -> Dict:
        """Check if user can use chatbot (API key or free tier)"""
        # If user has API key, unlimited usage
        if user_settings and user_settings.get('gemini_api_key'):
            return {'allowed': True, 'has_api_key': True, 'remaining': -1}
        
        # Check system API key
        from config.settings import GEMINI_API_KEY
        if GEMINI_API_KEY:
            # System has API key, check free tier limit
            daily_usage = self._get_user_daily_usage(user_id)
            remaining = max(0, self.FREE_DAILY_LIMIT - daily_usage)
            return {
                'allowed': remaining > 0,
                'has_api_key': False,
                'remaining': remaining,
                'limit': self.FREE_DAILY_LIMIT
            }
        
        return {'allowed': False, 'has_api_key': False, 'remaining': 0}
    
    def check_email_config(self, user_id: int) -> Dict:
        """Check if user has configured email settings"""
        try:
            user_settings = self.database.get_user_settings(user_id)
            has_email = bool(user_settings and user_settings.get('sender_email'))
            has_password = bool(user_settings and user_settings.get('sender_password'))
            
            return {
                'configured': has_email and has_password,
                'has_email': has_email,
                'has_password': has_password,
                'message': None if (has_email and has_password) else 
                          '⚠️ Bạn chưa cấu hình email. Vui lòng vào "Hồ sơ & API Keys" để thiết lập Email và App Password trước khi gửi email.'
            }
        except Exception as e:
            logger.error(f"Error checking email config: {e}")
            return {'configured': False, 'message': 'Không thể kiểm tra cấu hình email'}
    
    def _get_all_emails_admin(self) -> List[Dict]:
        """Get all emails from all users (admin only) with responses"""
        try:
            emails = self.database.query_raw(
                """SELECT DISTINCT ON (e.id) e.*, 
                          u.username as user_name, u.email as user_email,
                          r.response_body, r.response_subject,
                          r.analysis, r.received_at as response_received_at
                   FROM sent_emails e 
                   LEFT JOIN users u ON e.user_id = u.id 
                   LEFT JOIN responses r ON e.id = r.sent_email_id
                   ORDER BY e.id, r.received_at DESC NULLS LAST"""
            )
            # Sort by sent_at descending after DISTINCT ON
            result = sorted(emails or [], key=lambda x: x.get('sent_at', ''), reverse=True)
            return result
        except Exception as e:
            logger.error(f"Error getting all emails for admin: {e}")
            return []
    
    def _get_all_cv_evaluations_admin(self) -> List[Dict]:
        """Get all CV evaluations from all users (admin only)"""
        try:
            evaluations = self.database.query_raw(
                """SELECT cv.*, u.username as user_name, u.email as user_email 
                   FROM cv_evaluations cv 
                   LEFT JOIN users u ON cv.user_id = u.id 
                   ORDER BY cv.created_at DESC"""
            )
            return evaluations or []
        except Exception as e:
            logger.error(f"Error getting all CV evaluations for admin: {e}")
            return []
    
    def _get_user_statistics_admin(self) -> Dict:
        """Get comprehensive user statistics (admin only)"""
        try:
            # Get basic user info
            users = self.database.query_raw(
                """SELECT id, username, email, full_name, role, is_active, 
                          created_at, last_login 
                   FROM users ORDER BY created_at DESC"""
            )
            
            total_users = len(users) if users else 0
            active_users = sum(1 for u in users if u.get('is_active')) if users else 0
            admin_count = sum(1 for u in users if u.get('role') == 'admin') if users else 0
            
            # Get activity stats per user
            user_activity = self.database.query_raw(
                """SELECT u.id, u.username, u.email, u.full_name, u.role,
                          COALESCE(e.email_count, 0) as email_count,
                          COALESCE(e.responded_count, 0) as responded_count,
                          COALESCE(c.cv_count, 0) as cv_count,
                          COALESCE(c.qualified_count, 0) as qualified_count,
                          u.last_login, u.created_at
                   FROM users u
                   LEFT JOIN (
                       SELECT user_id, 
                              COUNT(*) as email_count,
                              SUM(CASE WHEN response_received THEN 1 ELSE 0 END) as responded_count
                       FROM sent_emails 
                       GROUP BY user_id
                   ) e ON u.id = e.user_id
                   LEFT JOIN (
                       SELECT user_id,
                              COUNT(*) as cv_count,
                              SUM(CASE WHEN is_qualified THEN 1 ELSE 0 END) as qualified_count
                       FROM cv_evaluations
                       GROUP BY user_id
                   ) c ON u.id = c.user_id
                   ORDER BY (COALESCE(e.email_count, 0) + COALESCE(c.cv_count, 0)) DESC"""
            ) or []
            
            # Top active users (by total activity)
            top_active_users = []
            for u in user_activity[:10]:
                top_active_users.append({
                    'id': u.get('id'),
                    'name': u.get('full_name') or u.get('username') or u.get('email', '').split('@')[0],
                    'email': u.get('email'),
                    'role': u.get('role'),
                    'email_count': u.get('email_count', 0),
                    'responded_count': u.get('responded_count', 0),
                    'cv_count': u.get('cv_count', 0),
                    'qualified_count': u.get('qualified_count', 0),
                    'total_activity': (u.get('email_count', 0) or 0) + (u.get('cv_count', 0) or 0),
                    'last_login': str(u.get('last_login', ''))[:19] if u.get('last_login') else 'Chưa đăng nhập'
                })
            
            # Calculate totals
            total_emails_all = sum(u.get('email_count', 0) or 0 for u in user_activity)
            total_cv_all = sum(u.get('cv_count', 0) or 0 for u in user_activity)
            
            return {
                'total_users': total_users,
                'active_users': active_users,
                'admin_count': admin_count,
                'user_count': total_users - admin_count,
                'inactive_count': total_users - active_users,
                'total_emails_all': total_emails_all,
                'total_cv_all': total_cv_all,
                'top_active_users': top_active_users,
                'users_list': users[:10] if users else []
            }
        except Exception as e:
            logger.error(f"Error getting user statistics: {e}")
            return {}
        
    def get_email_statistics(self, user_id: int, time_range: str = None, is_admin: bool = False) -> Dict:
        """Get comprehensive email statistics for a user (or all users if admin)"""
        try:
            # Get emails - all for admin, user-specific otherwise
            if is_admin:
                emails = self._get_all_emails_admin()
            else:
                emails = self.database.get_all_emails(user_id)
            
            # Filter by time range if specified
            if time_range:
                emails = self._filter_by_time_range(emails, time_range)
            
            # Calculate statistics
            total_sent = len(emails)
            responded = sum(1 for e in emails if e.get('response_received'))
            pending = total_sent - responded
            
            # Calculate response rate
            response_rate = (responded / total_sent * 100) if total_sent > 0 else 0
            
            # Analyze sentiments from responses
            sentiments = {'positive': 0, 'negative': 0, 'neutral': 0}
            decisions = {'agreed': 0, 'disagreed': 0, 'undecided': 0, 'needs_more_info': 0}
            
            for email in emails:
                if email.get('response_received') and email.get('analysis'):
                    analysis = email['analysis']
                    if isinstance(analysis, str):
                        try:
                            analysis = json.loads(analysis)
                        except:
                            continue
                    
                    sentiment = analysis.get('sentiment', '').lower()
                    if 'positive' in sentiment or 'tích cực' in sentiment:
                        sentiments['positive'] += 1
                    elif 'negative' in sentiment or 'tiêu cực' in sentiment:
                        sentiments['negative'] += 1
                    else:
                        sentiments['neutral'] += 1
                    
                    decision = analysis.get('decision', '').lower()
                    if 'agree' in decision or 'đồng ý' in decision:
                        decisions['agreed'] += 1
                    elif 'disagree' in decision or 'không đồng ý' in decision or 'từ chối' in decision:
                        decisions['disagreed'] += 1
                    elif 'more_info' in decision or 'thêm thông tin' in decision:
                        decisions['needs_more_info'] += 1
                    else:
                        decisions['undecided'] += 1
            
            # Get emails by date for time series
            emails_by_date = self._group_emails_by_date(emails)
            
            # Get top recipients
            top_recipients = self._get_top_recipients(emails)
            
            # Get emails by purpose
            emails_by_purpose = self._group_by_purpose(emails)
            
            return {
                'total_sent': total_sent,
                'responded': responded,
                'pending': pending,
                'failed': 0,  # Could track failed emails if needed
                'response_rate': round(response_rate, 2),
                'sentiments': sentiments,
                'decisions': decisions,
                'emails_by_date': emails_by_date,
                'top_recipients': top_recipients,
                'emails_by_purpose': emails_by_purpose,
                'time_range': time_range or 'all',
                'is_admin_view': is_admin
            }
        except Exception as e:
            logger.error(f"Error getting email statistics: {e}")
            return {}
    
    def get_cv_statistics(self, user_id: int, is_admin: bool = False) -> Dict:
        """Get CV evaluation statistics (all users if admin)"""
        try:
            if is_admin:
                evaluations = self._get_all_cv_evaluations_admin()
            else:
                evaluations = self.database.get_all_cv_evaluations(user_id)
            
            total = len(evaluations)
            qualified = sum(1 for e in evaluations if e.get('is_qualified'))
            not_qualified = total - qualified
            emails_sent = sum(1 for e in evaluations if e.get('email_sent'))
            
            # Score distribution
            score_ranges = {
                '0-50': 0,
                '51-70': 0,
                '71-84': 0,
                '85-100': 0
            }
            
            for ev in evaluations:
                score = ev.get('overall_score', 0)
                if score <= 50:
                    score_ranges['0-50'] += 1
                elif score <= 70:
                    score_ranges['51-70'] += 1
                elif score <= 84:
                    score_ranges['71-84'] += 1
                else:
                    score_ranges['85-100'] += 1
            
            # Average score
            avg_score = sum(e.get('overall_score', 0) for e in evaluations) / total if total > 0 else 0
            
            # By job title
            by_job_title = {}
            for ev in evaluations:
                job = ev.get('job_title', 'Không xác định')
                if job not in by_job_title:
                    by_job_title[job] = {'total': 0, 'qualified': 0}
                by_job_title[job]['total'] += 1
                if ev.get('is_qualified'):
                    by_job_title[job]['qualified'] += 1
            
            return {
                'total': total,
                'qualified': qualified,
                'not_qualified': not_qualified,
                'qualification_rate': round(qualified / total * 100, 2) if total > 0 else 0,
                'emails_sent': emails_sent,
                'average_score': round(avg_score, 2),
                'score_distribution': score_ranges,
                'by_job_title': by_job_title,
                'is_admin_view': is_admin
            }
        except Exception as e:
            logger.error(f"Error getting CV statistics: {e}")
            return {}
    
    def _format_recent_emails(self, emails: List[Dict]) -> str:
        """Format recent emails for AI context with response details"""
        if not emails:
            return "Chưa có email nào được gửi."
        
        result = []
        for i, email in enumerate(emails, 1):
            sent_at = email.get('sent_at', 'N/A')
            if isinstance(sent_at, datetime):
                sent_at = sent_at.strftime('%d/%m/%Y %H:%M')
            elif isinstance(sent_at, str) and len(sent_at) > 16:
                sent_at = sent_at[:16].replace('T', ' ')
            
            has_response = email.get('response_received')
            status = "✅ Đã có phản hồi" if has_response else "⏳ Chờ phản hồi"
            
            email_info = f"""
  {i}. Email ID #{email.get('id')}
     - Người nhận: {email.get('recipient_email', 'N/A')}
     - Tiêu đề: {email.get('subject', 'Không có tiêu đề')[:50]}
     - Gửi lúc: {sent_at}
     - Trạng thái: {status}"""
            
            # Include response details if available
            if has_response and email.get('response_body'):
                response_subject = email.get('response_subject', 'Re: ' + (email.get('subject') or ''))
                response_body = email.get('response_body', '')[:500]  # Limit to 500 chars
                received_at = email.get('response_received_at', '')
                if isinstance(received_at, datetime):
                    received_at = received_at.strftime('%d/%m/%Y %H:%M')
                elif isinstance(received_at, str) and len(received_at) > 16:
                    received_at = received_at[:16].replace('T', ' ')
                
                email_info += f"""
     📬 PHẢN HỒI:
        - Nhận lúc: {received_at}
        - Tiêu đề phản hồi: {response_subject[:50]}
        - Nội dung phản hồi: {response_body}"""
            
            result.append(email_info)
        
        return "\n".join(result)
    
    def _filter_by_time_range(self, emails: List[Dict], time_range: str) -> List[Dict]:
        """Filter emails by time range"""
        now = datetime.now()
        
        ranges = {
            'today': timedelta(days=1),
            'week': timedelta(weeks=1),
            'month': timedelta(days=30),
            '3months': timedelta(days=90),
            'year': timedelta(days=365)
        }
        
        if time_range not in ranges:
            return emails
        
        cutoff = now - ranges[time_range]
        
        filtered = []
        for email in emails:
            try:
                sent_at = email.get('sent_at')
                if sent_at:
                    if isinstance(sent_at, str):
                        # Try multiple formats
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d']:
                            try:
                                sent_date = datetime.strptime(sent_at[:19], fmt)
                                break
                            except:
                                continue
                        else:
                            continue
                    else:
                        sent_date = sent_at
                    
                    if sent_date >= cutoff:
                        filtered.append(email)
            except Exception as e:
                logger.warning(f"Error parsing date: {e}")
                continue
        
        return filtered
    
    def _group_emails_by_date(self, emails: List[Dict]) -> List[Dict]:
        """Group emails by date for time series chart"""
        by_date = {}
        
        for email in emails:
            try:
                sent_at = email.get('sent_at', '')
                if sent_at:
                    date_str = str(sent_at)[:10]
                    if date_str not in by_date:
                        by_date[date_str] = {'sent': 0, 'responded': 0}
                    by_date[date_str]['sent'] += 1
                    if email.get('response_received'):
                        by_date[date_str]['responded'] += 1
            except:
                continue
        
        # Sort by date and return as list
        sorted_dates = sorted(by_date.items())
        return [{'date': d, 'sent': v['sent'], 'responded': v['responded']} for d, v in sorted_dates]
    
    def _get_top_recipients(self, emails: List[Dict], limit: int = 5) -> List[Dict]:
        """Get top email recipients"""
        recipients = {}
        
        for email in emails:
            recipient = email.get('recipient_email', '')
            name = email.get('recipient_name', '')
            if recipient:
                if recipient not in recipients:
                    recipients[recipient] = {'email': recipient, 'name': name, 'count': 0, 'responded': 0}
                recipients[recipient]['count'] += 1
                if email.get('response_received'):
                    recipients[recipient]['responded'] += 1
        
        # Sort by count and return top N
        sorted_recipients = sorted(recipients.values(), key=lambda x: x['count'], reverse=True)
        return sorted_recipients[:limit]
    
    def _group_by_purpose(self, emails: List[Dict]) -> Dict:
        """Group emails by purpose/category"""
        purposes = {}
        
        for email in emails:
            purpose = email.get('purpose', 'Khác')
            # Truncate long purposes
            if len(purpose) > 50:
                purpose = purpose[:47] + '...'
            
            if purpose not in purposes:
                purposes[purpose] = {'count': 0, 'responded': 0}
            purposes[purpose]['count'] += 1
            if email.get('response_received'):
                purposes[purpose]['responded'] += 1
        
        return purposes
    
    def _get_guide_content(self) -> str:
        """Get comprehensive guide content for the chatbot"""
        return """
=== HƯỚNG DẪN SỬ DỤNG HỆ THỐNG EMAIL AI AGENT ===

📧 **1. SOẠN VÀ GỬI EMAIL**
- Vào menu "Soạn Email" từ thanh bên trái
- Nhập thông tin người gửi (tên, chức vụ, công ty)
- Nhập thông tin người nhận (email, tên)
- Mô tả mục đích email, AI sẽ tự động soạn nội dung
- Xem trước và gửi email

📋 **2. ĐÁNH GIÁ CV ỨNG VIÊN**
- Vào menu "Đánh giá CV"
- Upload file CV (PDF, DOCX, TXT) hoặc paste nội dung
- Nhập tiêu chí tuyển dụng và vị trí
- AI sẽ đánh giá và cho điểm từ 0-100
- Nếu điểm ≥85%, tự động gửi thư mời phỏng vấn

📊 **3. GIÁM SÁT PHẢN HỒI**
- Vào menu "Giám sát phản hồi"
- Hệ thống tự động kiểm tra email phản hồi
- AI phân tích cảm xúc và quyết định từ phản hồi
- Thông báo realtime qua WebSocket

📈 **4. PHÂN TÍCH YOUTUBE**
- Vào menu "Phân tích YouTube"
- Nhập URL kênh YouTube
- Xem thống kê: subscribers, views, videos
- AI ước tính thu nhập và phân tích xu hướng

🤖 **5. CHATBOT THỐNG KÊ** (Bạn đang ở đây!)
- Hỏi về thống kê email, CV
- Yêu cầu vẽ biểu đồ
- Xuất dữ liệu ra Excel
- Hỏi hướng dẫn sử dụng

=== HƯỚNG DẪN THIẾT LẬP API VÀ EMAIL ===

🔑 **THIẾT LẬP EMAIL GỬI (App Password)**

📧 **Gmail:**
1. Truy cập https://myaccount.google.com/security
2. Bật "Xác minh 2 bước" (2-Step Verification)
3. Truy cập https://myaccount.google.com/apppasswords
4. Chọn "Select app" → "Mail"
5. Chọn "Select device" → "Other" → Nhập "Email AI Agent"
6. Nhấn "Generate" → Sao chép mật khẩu 16 ký tự
7. Vào Hồ sơ & API Keys → Nhập email và App Password

📧 **Outlook/Hotmail:**
1. Truy cập https://account.microsoft.com/security
2. Bật Xác minh 2 bước
3. Vào "App passwords" → Tạo mật khẩu mới
4. Sao chép và sử dụng mật khẩu được tạo
5. SMTP: smtp.office365.com, Port: 587
6. IMAP: outlook.office365.com, Port: 993

📧 **Yahoo Mail:**
1. Truy cập https://login.yahoo.com/account/security
2. Bật Xác minh 2 bước
3. Nhấn "Generate app password"
4. Chọn "Other app", nhập tên, nhấn "Generate"
5. SMTP: smtp.mail.yahoo.com, Port: 587
6. IMAP: imap.mail.yahoo.com, Port: 993

🤖 **THIẾT LẬP API AI**

🔹 **Google Gemini API (Miễn phí):**
1. Truy cập https://makersuite.google.com/app/apikey
2. Đăng nhập bằng tài khoản Google
3. Nhấn "Create API Key"
4. Sao chép API Key
5. Vào Hồ sơ & API Keys → Chọn Gemini → Dán API Key

🔹 **Azure OpenAI:**
1. Truy cập https://portal.azure.com
2. Tạo Azure OpenAI resource
3. Vào Keys and Endpoint → Sao chép KEY 1 và Endpoint
4. Deploy model GPT-4 hoặc GPT-3.5
5. Vào Hồ sơ & API Keys → Chọn Azure → Nhập thông tin

🔹 **OpenAI API:**
1. Truy cập https://platform.openai.com/api-keys
2. Nhấn "Create new secret key"
3. Sao chép API Key (chỉ hiện 1 lần!)
4. Vào Hồ sơ & API Keys → Chọn OpenAI → Dán API Key

=== CẤU HÌNH SMTP/IMAP PHỔ BIẾN ===

| Provider | SMTP Host | SMTP Port | IMAP Host | IMAP Port |
|----------|-----------|-----------|-----------|-----------|
| Gmail | smtp.gmail.com | 587 | imap.gmail.com | 993 |
| Outlook | smtp.office365.com | 587 | outlook.office365.com | 993 |
| Yahoo | smtp.mail.yahoo.com | 587 | imap.mail.yahoo.com | 993 |
| iCloud | smtp.mail.me.com | 587 | imap.mail.me.com | 993 |

=== MẸO SỬ DỤNG ===

💡 **Tips:**
- Luôn test gửi email cho chính mình trước
- Kiểm tra thư mục Spam nếu không nhận được email
- Sử dụng mô tả chi tiết để AI soạn email tốt hơn
- Cập nhật tiêu chí tuyển dụng rõ ràng khi đánh giá CV
- Xuất Excel để lưu trữ và báo cáo

⚠️ **Lưu ý bảo mật:**
- Không chia sẻ App Password với người khác
- API Key nên được bảo mật
- Đổi mật khẩu định kỳ
"""

    def _is_guide_query(self, query: str) -> bool:
        """Check if query is asking for help/guide"""
        guide_keywords = [
            'hướng dẫn', 'cách sử dụng', 'cách dùng', 'làm sao', 'làm thế nào',
            'thiết lập', 'cài đặt', 'setup', 'config', 'cấu hình',
            'api', 'api key', 'gemini', 'openai', 'azure',
            'app password', 'mật khẩu ứng dụng', 'password',
            'gmail', 'outlook', 'yahoo', 'email gửi',
            'smtp', 'imap', 'port',
            'help', 'trợ giúp', 'hỗ trợ',
            'bắt đầu', 'getting started', 'tutorial',
            'tính năng', 'chức năng', 'feature'
        ]
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in guide_keywords)

    def _get_conversation_history(self, session_id: int, max_messages: int = 20) -> str:
        """Get conversation history for context"""
        try:
            messages = self.database.get_session_messages(session_id)
            if not messages:
                return ""
            
            # Limit to last N messages to avoid token overflow
            recent_messages = messages[-max_messages:] if len(messages) > max_messages else messages
            
            # Exclude the current message (last user message just saved)
            if recent_messages and recent_messages[-1].get('role') == 'user':
                recent_messages = recent_messages[:-1]
            
            if not recent_messages:
                return ""
            
            history_text = "=== LỊCH SỬ HỘI THOẠI TRƯỚC ĐÓ ===\n"
            for msg in recent_messages:
                role = "Người dùng" if msg.get('role') == 'user' else "Trợ lý AI"
                content = msg.get('content', '')
                # Truncate very long messages
                if len(content) > 500:
                    content = content[:500] + "..."
                history_text += f"\n{role}: {content}\n"
            
            history_text += "\n=== KẾT THÚC LỊCH SỬ ===\n"
            return history_text
            
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return ""

    def process_query(self, user_id: int, query: str, user_settings: Dict = None, 
                       is_admin: bool = False, session_id: int = None) -> Dict:
        """Process user query and return appropriate response with data"""
        try:
            # Get or create session
            if session_id is None:
                session_id = self.database.get_or_create_active_session(user_id)
            
            # Save user message
            self.database.save_chat_message(session_id, user_id, 'user', query)
            
            # Load conversation history for context
            conversation_history = self._get_conversation_history(session_id)
            
            # Check if this is a guide/help query
            is_guide_query = self._is_guide_query(query)
            
            # Get user data - admin can see all data
            email_stats = self.get_email_statistics(user_id, is_admin=is_admin)
            cv_stats = self.get_cv_statistics(user_id, is_admin=is_admin)
            user_stats = self._get_user_statistics_admin() if is_admin else None
            
            # Get recent emails for context
            recent_emails = self.database.get_recent_emails(user_id, limit=5)
            recent_emails_context = self._format_recent_emails(recent_emails)
            
            # Build context for AI
            admin_context = ""
            if is_admin and user_stats:
                top_users = user_stats.get('top_active_users', [])[:5]
                top_users_text = ""
                for i, u in enumerate(top_users, 1):
                    top_users_text += f"  {i}. {u.get('name')} ({u.get('role')}): {u.get('email_count', 0)} email, {u.get('cv_count', 0)} CV\n"
                
                admin_context = f"""
=== THỐNG KÊ NGƯỜI DÙNG HỆ THỐNG (CHỈ ADMIN) ===
- Tổng số người dùng: {user_stats.get('total_users', 0)}
- Người dùng đang hoạt động: {user_stats.get('active_users', 0)}
- Người dùng không hoạt động: {user_stats.get('inactive_count', 0)}
- Số admin: {user_stats.get('admin_count', 0)}
- Số user thường: {user_stats.get('user_count', 0)}

📊 TỔNG HOẠT ĐỘNG HỆ THỐNG:
- Tổng email đã gửi (tất cả user): {user_stats.get('total_emails_all', 0)}
- Tổng CV đã đánh giá (tất cả user): {user_stats.get('total_cv_all', 0)}

🏆 TOP NGƯỜI DÙNG HOẠT ĐỘNG NHIỀU NHẤT:
{top_users_text if top_users_text else '  Chưa có dữ liệu hoạt động'}

⚠️ LƯU Ý: Bạn đang xem dữ liệu TOÀN BỘ HỆ THỐNG với quyền Admin.
"""
            
            # Add guide content if user is asking for help
            guide_context = ""
            if is_guide_query:
                guide_context = self._get_guide_content()
            
            view_note = "(Dữ liệu toàn hệ thống - Admin View)" if is_admin else "(Dữ liệu cá nhân)"
            
            context = f"""
Bạn là chatbot trợ lý thông minh của hệ thống Email AI Agent. Bạn có thể:
1. Trả lời câu hỏi về thống kê email và CV
2. Hướng dẫn sử dụng hệ thống
3. Hướng dẫn thiết lập API (Gemini, OpenAI, Azure)
4. Hướng dẫn cấu hình email (Gmail, Outlook, Yahoo App Password)
5. Vẽ biểu đồ và xuất Excel

{guide_context}
{admin_context}

=== THỐNG KÊ EMAIL {view_note} ===
- Tổng số email đã gửi: {email_stats.get('total_sent', 0)}
- Số email đã nhận phản hồi: {email_stats.get('responded', 0)}
- Số email đang chờ phản hồi: {email_stats.get('pending', 0)}
- Tỷ lệ phản hồi: {email_stats.get('response_rate', 0)}%

Phân tích cảm xúc phản hồi:
- Tích cực: {email_stats.get('sentiments', {}).get('positive', 0)}
- Tiêu cực: {email_stats.get('sentiments', {}).get('negative', 0)}
- Trung tính: {email_stats.get('sentiments', {}).get('neutral', 0)}

Quyết định từ phản hồi:
- Đồng ý: {email_stats.get('decisions', {}).get('agreed', 0)}
- Từ chối: {email_stats.get('decisions', {}).get('disagreed', 0)}
- Chưa quyết định: {email_stats.get('decisions', {}).get('undecided', 0)}
- Cần thêm thông tin: {email_stats.get('decisions', {}).get('needs_more_info', 0)}

=== DANH SÁCH EMAIL GẦN NHẤT ===
{recent_emails_context}

Top 5 người nhận email:
{json.dumps(email_stats.get('top_recipients', []), ensure_ascii=False, indent=2)}

=== THỐNG KÊ ĐÁNH GIÁ CV {view_note} ===
- Tổng số CV đã đánh giá: {cv_stats.get('total', 0)}
- Số ứng viên đạt yêu cầu (≥85%): {cv_stats.get('qualified', 0)}
- Số ứng viên chưa đạt: {cv_stats.get('not_qualified', 0)}
- Tỷ lệ đạt: {cv_stats.get('qualification_rate', 0)}%
- Điểm trung bình: {cv_stats.get('average_score', 0)}
- Số email mời phỏng vấn đã gửi: {cv_stats.get('emails_sent', 0)}

Phân bố điểm CV:
{json.dumps(cv_stats.get('score_distribution', {}), ensure_ascii=False, indent=2)}

{conversation_history}

=== CÂU HỎI HIỆN TẠI CỦA NGƯỜI DÙNG ===
{query}

=== HƯỚNG DẪN TRẢ LỜI ===
- Trả lời tự nhiên, thân thiện bằng tiếng Việt
- NHỚ CONTEXT của cuộc hội thoại trước đó để trả lời liên quan
- Nếu người dùng hỏi tiếp theo hoặc đề cập đến nội dung trước, hãy dựa vào lịch sử để trả lời
- Nếu hỏi về hướng dẫn/thiết lập: Cung cấp hướng dẫn chi tiết từng bước
- Nếu hỏi về thống kê: Cung cấp số liệu và phân tích
- Nếu hỏi về biểu đồ/xuất file: Đề cập bạn có thể hỗ trợ
- Sử dụng emoji để làm nổi bật thông tin quan trọng
- Định dạng với bullet points cho dễ đọc

=== TÍNH NĂNG XEM TRẠNG THÁI EMAIL VÀ PHẢN HỒI ===
Khi người dùng hỏi về trạng thái email gần nhất/mới nhất:
- Hiển thị thông tin chi tiết của email gần nhất từ DANH SÁCH EMAIL GẦN NHẤT
- Bao gồm: người nhận, tiêu đề, thời gian gửi, trạng thái phản hồi
- Set show_email_status=true và email_id=<id của email> trong INTENT

Khi người dùng muốn XEM CHI TIẾT PHẢN HỒI:
- Nếu email đã có phản hồi (có mục 📬 PHẢN HỒI trong danh sách), HIỂN THỊ NGAY nội dung phản hồi trong câu trả lời
- Trích dẫn đầy đủ: tiêu đề phản hồi, thời gian nhận, NỘI DUNG PHẢN HỒI
- Định dạng đẹp với quote hoặc blockquote
- Set show_email_status=true và email_id để hiện card chi tiết

=== TÍNH NĂNG GỬI EMAIL ===
Bạn có thể giúp người dùng soạn và gửi email. Khi người dùng muốn gửi email:
- LUÔN set show_email_form=true để hiện form gửi email
- Nếu user cung cấp thông tin (email, mục đích) thì điền vào email_data
- Nếu chưa có thông tin, hướng dẫn họ điền form hoặc chat thêm

=== QUAN TRỌNG: PHÂN TÍCH Ý ĐỊNH ===
Sau khi trả lời, hãy thêm một dòng ở cuối response với format:
[INTENT: chart_type=<loại>, show_chart=<true/false>, show_export=<true/false>, show_email_form=<true/false>, show_email_status=<true/false>, email_id=<id_hoặc_none>, email_data=<json_hoặc_none>]

Các chart_type có thể là:
- "pie", "bar", "horizontalBar", "line", "doughnut", "radar", "polarArea"
- "cv", "cv_qualified", "user_stats", "user_activity"
- "table_email", "table_cv", "table_users", "stats_cards", "progress", "comparison"
- "none": không cần biểu đồ

Khi người dùng muốn GỬI EMAIL (gửi mail, soạn email, compose, send email...):
- LUÔN set show_email_form=true
- email_data chứa thông tin nếu có: {{"to_email": "...", "to_name": "...", "purpose": "...", "tone": "formal/friendly/casual", "language": "vi/en"}}
- Nếu chưa có thông tin: email_data=none

Khi người dùng muốn XEM TRẠNG THÁI EMAIL GẦN NHẤT/MỚI NHẤT:
- Set show_email_status=true và email_id=<id của email gần nhất từ danh sách>
- Hiển thị đầy đủ thông tin: người nhận, tiêu đề, thời gian, trạng thái

Khi người dùng muốn XEM CHI TIẾT PHẢN HỒI:
- HIỂN THỊ NGAY trong câu trả lời: nội dung phản hồi từ mục 📬 PHẢN HỒI trong danh sách email
- Định dạng đẹp, trích dẫn nội dung phản hồi đầy đủ
- Set show_email_status=true và email_id để hiện thêm card chi tiết

Ví dụ:
- "Gửi email cho abc@gmail.com về việc họp" → [INTENT: chart_type=none, show_chart=false, show_export=false, show_email_form=true, show_email_status=false, email_id=none, email_data={{"to_email":"abc@gmail.com","purpose":"mời họp","tone":"formal","language":"vi"}}]
- "Tôi muốn gửi email" → [INTENT: chart_type=none, show_chart=false, show_export=false, show_email_form=true, show_email_status=false, email_id=none, email_data=none]
- "Xem trạng thái email gần nhất" → [INTENT: chart_type=none, show_chart=false, show_export=false, show_email_form=false, show_email_status=true, email_id=<id_email_gần_nhất>, email_data=none]
- "Xem chi tiết phản hồi email gần nhất" → Hiển thị nội dung phản hồi trong text + [INTENT: chart_type=none, show_chart=false, show_export=false, show_email_form=false, show_email_status=true, email_id=<id_email>, email_data=none]
- "Người ta phản hồi gì?" → Hiển thị nội dung phản hồi đầy đủ trong câu trả lời + [INTENT: show_email_status=true, email_id=<id>...]
- "Thống kê email" → [INTENT: chart_type=stats_cards, show_chart=true, show_export=false, show_email_form=false, show_email_status=false, email_id=none, email_data=none]
"""
            
            # Generate AI response with intent analysis
            ai_response = self._generate_ai_response(context, user_settings)
            
            # Parse intent from AI response
            intent = self._parse_ai_intent(ai_response)
            
            # Clean the response (remove intent line)
            clean_response = self._clean_response(ai_response)
            
            # Get chart data if AI decided to show chart
            chart_data = None
            if intent['show_chart'] and intent['chart_type'] != 'none':
                chart_data = self.get_chart_data(user_id, intent['chart_type'], is_admin=is_admin)
            
            response = {
                'success': True,
                'message': clean_response,
                'data': {
                    'email_stats': email_stats,
                    'cv_stats': cv_stats,
                    'user_stats': user_stats if is_admin else None
                },
                'is_admin': is_admin,
                'show_chart': intent['show_chart'],
                'show_export': intent['show_export'],
                'show_email_form': intent.get('show_email_form', False),
                'show_email_status': intent.get('show_email_status', False),
                'email_id': intent.get('email_id'),
                'email_data': intent.get('email_data'),
                'chart_type': intent['chart_type'],
                'chart_data': chart_data,
                'session_id': session_id,
                'timestamp': datetime.now().isoformat()
            }
            
            # Save bot response
            self.database.save_chat_message(
                session_id, user_id, 'bot', clean_response,
                has_chart=intent['show_chart'], chart_type=intent['chart_type'],
                chart_data=chart_data, has_export=intent['show_export'],
                has_email_form=intent.get('show_email_form', False),
                email_data=intent.get('email_data')
            )
            
            # Update session title if this is the first message
            self.database.generate_session_title(session_id, user_id)
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                'success': False,
                'message': f'Xin lỗi, đã có lỗi xảy ra: {str(e)}',
                'data': {}
            }
    
    def _parse_ai_intent(self, response: str) -> Dict:
        """Parse AI intent from response"""
        import re
        import json
        
        default_intent = {
            'chart_type': 'none',
            'show_chart': False,
            'show_export': False,
            'show_email_form': False,
            'show_email_status': False,
            'email_id': None,
            'email_data': None
        }
        
        try:
            # Try to find intent line with all parameters including email_status
            # Pattern: [INTENT: chart_type=xxx, show_chart=xxx, show_export=xxx, show_email_form=xxx, show_email_status=xxx, email_id=xxx, email_data=xxx]
            intent_match = re.search(
                r'\[INTENT:\s*chart_type=([^,]+),\s*show_chart=([^,]+),\s*show_export=([^,]+),\s*show_email_form=([^,]+),\s*show_email_status=([^,]+),\s*email_id=([^,\]]+)(?:,\s*email_data=(.+?))?\]', 
                response
            )
            
            if intent_match:
                chart_type = intent_match.group(1).strip().lower()
                show_chart = intent_match.group(2).strip().lower() == 'true'
                show_export = intent_match.group(3).strip().lower() == 'true'
                show_email_form = intent_match.group(4).strip().lower() == 'true'
                show_email_status = intent_match.group(5).strip().lower() == 'true'
                email_id_str = intent_match.group(6).strip()
                email_data_str = intent_match.group(7).strip() if intent_match.group(7) else 'none'
                
                # Parse email_id
                email_id = None
                if email_id_str and email_id_str.lower() != 'none':
                    try:
                        email_id = int(email_id_str)
                    except:
                        email_id = None
                
                # Parse email_data JSON
                email_data = None
                if email_data_str and email_data_str.lower() != 'none':
                    try:
                        email_data_str = email_data_str.rstrip(']').strip()
                        email_data = json.loads(email_data_str)
                    except:
                        email_data = None
                
                return {
                    'chart_type': chart_type if chart_type != 'none' else 'none',
                    'show_chart': show_chart,
                    'show_export': show_export,
                    'show_email_form': show_email_form,
                    'show_email_status': show_email_status,
                    'email_id': email_id,
                    'email_data': email_data
                }
            
            # Try format with email_form but without email_status (backward compat)
            intent_match2 = re.search(
                r'\[INTENT:\s*chart_type=([^,]+),\s*show_chart=([^,]+),\s*show_export=([^,]+),\s*show_email_form=([^,\]]+)(?:,\s*email_data=(.+?))?\]', 
                response
            )
            
            if intent_match2:
                chart_type = intent_match2.group(1).strip().lower()
                show_chart = intent_match2.group(2).strip().lower() == 'true'
                show_export = intent_match2.group(3).strip().lower() == 'true'
                show_email_form = intent_match2.group(4).strip().lower() == 'true'
                email_data_str = intent_match2.group(5).strip() if intent_match2.group(5) else 'none'
                
                email_data = None
                if email_data_str and email_data_str.lower() != 'none':
                    try:
                        email_data_str = email_data_str.rstrip(']').strip()
                        email_data = json.loads(email_data_str)
                    except:
                        email_data = None
                
                return {
                    'chart_type': chart_type if chart_type != 'none' else 'none',
                    'show_chart': show_chart,
                    'show_export': show_export,
                    'show_email_form': show_email_form,
                    'show_email_status': False,
                    'email_id': None,
                    'email_data': email_data
                }
            
            # Try old format for backward compatibility (3 params only)
            old_match = re.search(r'\[INTENT:\s*chart_type=([^,]+),\s*show_chart=([^,]+),\s*show_export=([^\],]+)\]?', response)
            if old_match:
                chart_type = old_match.group(1).strip().lower()
                show_chart = old_match.group(2).strip().lower() == 'true'
                show_export = old_match.group(3).strip().lower() == 'true'
                
                return {
                    'chart_type': chart_type if chart_type != 'none' else 'none',
                    'show_chart': show_chart,
                    'show_export': show_export,
                    'show_email_form': False,
                    'show_email_status': False,
                    'email_id': None,
                    'email_data': None
                }
        except Exception as e:
            logger.error(f"Error parsing AI intent: {e}")
        
        return default_intent
    
    def _clean_response(self, response: str) -> str:
        """Remove intent line from response"""
        import re
        # Remove the intent line
        cleaned = re.sub(r'\n?\[INTENT:[^\]]+\]', '', response)
        return cleaned.strip()
    
    def _generate_ai_response(self, context: str, user_settings: Dict = None) -> str:
        """Generate AI response for the query"""
        try:
            import google.generativeai as genai
            from config.settings import GEMINI_API_KEY, GEMINI_MODEL
            
            # Use user's API key if available
            api_key = GEMINI_API_KEY
            if user_settings and user_settings.get('gemini_api_key'):
                api_key = user_settings['gemini_api_key']
            
            if not api_key:
                return "Xin lỗi, chưa cấu hình API key cho AI. Vui lòng kiểm tra cài đặt."
            
            genai.configure(api_key=api_key)
            
            model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                generation_config={
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "max_output_tokens": 2048,
                }
            )
            
            response = model.generate_content(context)
            return response.text
            
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            # Fallback to basic response
            return self._generate_basic_response(context)
    
    def _generate_basic_response(self, context: str) -> str:
        """Generate basic response without AI"""
        # Extract stats from context
        return """Dựa trên dữ liệu của bạn:
        
📊 **Tổng quan Email:**
- Xem phần thống kê bên phải để biết chi tiết
- Bạn có thể xem biểu đồ hoặc xuất file Excel

💡 **Gợi ý:**
- Hỏi "Vẽ biểu đồ số email theo ngày" để xem biểu đồ
- Hỏi "Xuất Excel" để tải dữ liệu

Tôi có thể giúp gì thêm cho bạn?"""
    
    def _determine_chart_type(self, query: str) -> str:
        """Determine the appropriate chart type based on query"""
        query_lower = query.lower()
        
        # User activity chart (admin) - more specific, check first
        if any(word in query_lower for word in ['hoạt động user', 'hoạt động người dùng', 'ai gửi', 'ai đánh giá', 
                                                  'top user', 'user nào', 'người dùng nào', 'activity']):
            return 'user_activity'
        
        # User statistics (admin only) - general user stats
        elif any(word in query_lower for word in ['user', 'người dùng', 'tài khoản', 'account', 'member', 'thành viên']):
            return 'user_stats'
        
        # Pie chart keywords
        elif any(word in query_lower for word in ['pie', 'tròn', 'cảm xúc', 'sentiment', 'phần trăm']):
            return 'pie'
        
        # Bar chart keywords
        elif any(word in query_lower for word in ['bar', 'cột', 'người nhận', 'recipient', 'top']):
            return 'bar'
        
        # Line chart keywords
        elif any(word in query_lower for word in ['line', 'đường', 'xu hướng', 'trend', 'theo ngày', 'thời gian']):
            return 'line'
        
        # Doughnut chart keywords
        elif any(word in query_lower for word in ['doughnut', 'donut', 'trạng thái', 'status']):
            return 'doughnut'
        
        # CV related charts
        elif any(word in query_lower for word in ['cv', 'ứng viên', 'điểm cv', 'phân bố điểm']):
            return 'cv'
        
        # CV qualification
        elif any(word in query_lower for word in ['đạt yêu cầu', 'qualified', 'tỷ lệ đạt']):
            return 'cv_qualified'
        
        # Decision analysis
        elif any(word in query_lower for word in ['quyết định', 'decision', 'đồng ý', 'từ chối']):
            return 'decision'
        
        # Radar/performance chart
        elif any(word in query_lower for word in ['radar', 'hiệu suất', 'performance', 'tổng quan hiệu suất']):
            return 'radar'
        
        else:
            return 'overview'  # Default to doughnut overview
    
    def generate_excel_data(self, user_id: int, data_type: str = 'all', is_admin: bool = False) -> bytes:
        """Generate Excel file with email/CV data (all data if admin) using xlsxwriter"""
        try:
            import xlsxwriter
            
            output = io.BytesIO()
            wb = xlsxwriter.Workbook(output, {'in_memory': True})
            
            # Styles
            header_format = wb.add_format({
                'bold': True,
                'font_color': 'white',
                'bg_color': '#4A90D9',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })
            cell_format = wb.add_format({
                'border': 1,
                'valign': 'vcenter'
            })
            bold_format = wb.add_format({'bold': True, 'font_size': 14})
            warning_format = wb.add_format({'bold': True, 'font_size': 12, 'font_color': 'red'})
            
            if data_type in ['all', 'emails']:
                # Email sheet
                sheet_name = 'Emails đã gửi' + (' (Tất cả)' if is_admin else '')
                ws_emails = wb.add_worksheet(sheet_name[:31])  # Excel sheet name max 31 chars
                
                if is_admin:
                    emails = self._get_all_emails_admin()
                else:
                    emails = self.database.get_all_emails(user_id)
                
                # Headers
                if is_admin:
                    headers = ['ID', 'User', 'Ngày gửi', 'Người nhận', 'Email', 'Tiêu đề', 'Mục đích', 'Đã phản hồi', 'Cảm xúc', 'Quyết định']
                else:
                    headers = ['ID', 'Ngày gửi', 'Người nhận', 'Email', 'Tiêu đề', 'Mục đích', 'Đã phản hồi', 'Cảm xúc', 'Quyết định']
                
                for col, header in enumerate(headers):
                    ws_emails.write(0, col, header, header_format)
                    ws_emails.set_column(col, col, 15)  # Default width
                
                # Data
                for row_num, email in enumerate(emails, 1):
                    analysis = email.get('analysis', {})
                    if isinstance(analysis, str):
                        try:
                            analysis = json.loads(analysis)
                        except:
                            analysis = {}
                    
                    col_offset = 1 if is_admin else 0
                    ws_emails.write(row_num, 0, email.get('id'), cell_format)
                    if is_admin:
                        ws_emails.write(row_num, 1, email.get('user_name', email.get('user_email', '')), cell_format)
                    ws_emails.write(row_num, 1 + col_offset, str(email.get('sent_at', ''))[:19], cell_format)
                    ws_emails.write(row_num, 2 + col_offset, email.get('recipient_name', ''), cell_format)
                    ws_emails.write(row_num, 3 + col_offset, email.get('recipient_email', ''), cell_format)
                    ws_emails.write(row_num, 4 + col_offset, email.get('subject', ''), cell_format)
                    ws_emails.write(row_num, 5 + col_offset, email.get('purpose', ''), cell_format)
                    ws_emails.write(row_num, 6 + col_offset, 'Có' if email.get('response_received') else 'Không', cell_format)
                    ws_emails.write(row_num, 7 + col_offset, analysis.get('sentiment', ''), cell_format)
                    ws_emails.write(row_num, 8 + col_offset, analysis.get('decision', ''), cell_format)
                
                # Adjust column widths
                ws_emails.set_column(0, 0, 8)   # ID
                ws_emails.set_column(1 + col_offset, 1 + col_offset, 18)  # Date
                ws_emails.set_column(4 + col_offset, 4 + col_offset, 30)  # Subject
            
            if data_type in ['all', 'cv']:
                # CV sheet
                sheet_name = 'Đánh giá CV' + (' (Tất cả)' if is_admin else '')
                ws_cv = wb.add_worksheet(sheet_name[:31])
                
                if is_admin:
                    evaluations = self._get_all_cv_evaluations_admin()
                else:
                    evaluations = self.database.get_all_cv_evaluations(user_id)
                
                # Headers
                if is_admin:
                    cv_headers = ['ID', 'User', 'Ngày đánh giá', 'Tên ứng viên', 'Email', 'Vị trí', 'Điểm', 'Đạt yêu cầu', 'Đã gửi email']
                else:
                    cv_headers = ['ID', 'Ngày đánh giá', 'Tên ứng viên', 'Email', 'Vị trí', 'Điểm', 'Đạt yêu cầu', 'Đã gửi email']
                
                for col, header in enumerate(cv_headers):
                    ws_cv.write(0, col, header, header_format)
                    ws_cv.set_column(col, col, 15)
                
                # Data
                for row_num, cv in enumerate(evaluations, 1):
                    col_offset = 1 if is_admin else 0
                    ws_cv.write(row_num, 0, cv.get('id'), cell_format)
                    if is_admin:
                        ws_cv.write(row_num, 1, cv.get('user_name', cv.get('user_email', '')), cell_format)
                    ws_cv.write(row_num, 1 + col_offset, str(cv.get('created_at', ''))[:19], cell_format)
                    ws_cv.write(row_num, 2 + col_offset, cv.get('candidate_name', ''), cell_format)
                    ws_cv.write(row_num, 3 + col_offset, cv.get('candidate_email', ''), cell_format)
                    ws_cv.write(row_num, 4 + col_offset, cv.get('job_title', ''), cell_format)
                    ws_cv.write(row_num, 5 + col_offset, cv.get('overall_score', 0), cell_format)
                    ws_cv.write(row_num, 6 + col_offset, 'Có' if cv.get('is_qualified') else 'Không', cell_format)
                    ws_cv.write(row_num, 7 + col_offset, 'Có' if cv.get('email_sent') else 'Không', cell_format)
            
            # Statistics sheet
            sheet_name = 'Thống kê' + (' (Toàn hệ thống)' if is_admin else '')
            ws_stats = wb.add_worksheet(sheet_name[:31])
            email_stats = self.get_email_statistics(user_id, is_admin=is_admin)
            cv_stats = self.get_cv_statistics(user_id, is_admin=is_admin)
            
            ws_stats.set_column(0, 0, 30)
            ws_stats.set_column(1, 1, 15)
            
            # Admin note
            if is_admin:
                ws_stats.write(0, 0, '⚠️ DỮ LIỆU TOÀN HỆ THỐNG (ADMIN VIEW)', warning_format)
                start_row = 2
            else:
                start_row = 0
            
            # Email stats
            ws_stats.write(start_row, 0, 'THỐNG KÊ EMAIL', bold_format)
            ws_stats.write(start_row + 1, 0, 'Tổng số email đã gửi:')
            ws_stats.write(start_row + 1, 1, email_stats.get('total_sent', 0))
            ws_stats.write(start_row + 2, 0, 'Số email đã nhận phản hồi:')
            ws_stats.write(start_row + 2, 1, email_stats.get('responded', 0))
            ws_stats.write(start_row + 3, 0, 'Số email đang chờ:')
            ws_stats.write(start_row + 3, 1, email_stats.get('pending', 0))
            ws_stats.write(start_row + 4, 0, 'Tỷ lệ phản hồi:')
            ws_stats.write(start_row + 4, 1, f"{email_stats.get('response_rate', 0)}%")
            
            # CV stats
            ws_stats.write(start_row + 6, 0, 'THỐNG KÊ CV', bold_format)
            ws_stats.write(start_row + 7, 0, 'Tổng số CV đã đánh giá:')
            ws_stats.write(start_row + 7, 1, cv_stats.get('total', 0))
            ws_stats.write(start_row + 8, 0, 'Số ứng viên đạt yêu cầu:')
            ws_stats.write(start_row + 8, 1, cv_stats.get('qualified', 0))
            ws_stats.write(start_row + 9, 0, 'Điểm trung bình:')
            ws_stats.write(start_row + 9, 1, cv_stats.get('average_score', 0))
            
            # Close workbook and get bytes
            wb.close()
            output.seek(0)
            
            return output.getvalue()
            
        except ImportError:
            logger.error("xlsxwriter not installed")
            raise Exception("Thư viện xlsxwriter chưa được cài đặt. Chạy: pip install xlsxwriter")
        except Exception as e:
            logger.error(f"Error generating Excel: {e}")
            raise e
    
    def get_chart_data(self, user_id: int, chart_type: str = 'overview', is_admin: bool = False) -> Dict:
        """Get data formatted for specific chart types (all data if admin)"""
        email_stats = self.get_email_statistics(user_id, is_admin=is_admin)
        cv_stats = self.get_cv_statistics(user_id, is_admin=is_admin)
        
        if chart_type == 'pie':
            # Sentiment pie chart
            return {
                'type': 'pie',
                'title': '🎯 Phân tích cảm xúc phản hồi',
                'labels': ['Tích cực 😊', 'Tiêu cực 😞', 'Trung tính 😐'],
                'data': [
                    email_stats.get('sentiments', {}).get('positive', 0),
                    email_stats.get('sentiments', {}).get('negative', 0),
                    email_stats.get('sentiments', {}).get('neutral', 0)
                ],
                'colors': ['#10b981', '#ef4444', '#f59e0b']
            }
        
        elif chart_type == 'bar':
            # Top recipients bar chart
            top_recipients = email_stats.get('top_recipients', [])
            
            # Fallback if no recipients
            if not top_recipients:
                return {
                    'type': 'bar',
                    'title': '📊 Top người nhận email nhiều nhất',
                    'labels': ['Chưa có dữ liệu'],
                    'datasets': [{
                        'label': 'Email đã gửi',
                        'data': [0],
                        'backgroundColor': 'rgba(99, 102, 241, 0.8)',
                        'borderColor': '#6366f1',
                        'borderWidth': 2,
                        'borderRadius': 8
                    }]
                }
            
            # Get proper labels - use name if available, otherwise use email
            labels = []
            for r in top_recipients:
                name = r.get('name', '').strip()
                email = r.get('email', '').strip()
                if name:
                    labels.append(name[:20])
                elif email:
                    # Shorten email if too long
                    if len(email) > 20:
                        labels.append(email[:17] + '...')
                    else:
                        labels.append(email)
                else:
                    labels.append('Unknown')
            
            return {
                'type': 'bar',
                'title': '📊 Top người nhận email nhiều nhất',
                'labels': labels,
                'datasets': [
                    {
                        'label': 'Email đã gửi',
                        'data': [r.get('count', 0) for r in top_recipients],
                        'backgroundColor': 'rgba(99, 102, 241, 0.8)',
                        'borderColor': '#6366f1',
                        'borderWidth': 2,
                        'borderRadius': 8
                    },
                    {
                        'label': 'Đã phản hồi',
                        'data': [r.get('responded', 0) for r in top_recipients],
                        'backgroundColor': 'rgba(16, 185, 129, 0.8)',
                        'borderColor': '#10b981',
                        'borderWidth': 2,
                        'borderRadius': 8
                    }
                ]
            }
        
        elif chart_type == 'line':
            # Emails by date line chart
            emails_by_date = email_stats.get('emails_by_date', [])
            return {
                'type': 'line',
                'title': '📈 Xu hướng email theo thời gian',
                'labels': [d.get('date', '') for d in emails_by_date[-30:]],
                'datasets': [
                    {
                        'label': 'Email đã gửi',
                        'data': [d.get('sent', 0) for d in emails_by_date[-30:]],
                        'borderColor': '#6366f1',
                        'backgroundColor': 'rgba(99, 102, 241, 0.1)',
                        'fill': True,
                        'tension': 0.4,
                        'pointRadius': 4,
                        'pointHoverRadius': 6
                    },
                    {
                        'label': 'Phản hồi nhận được',
                        'data': [d.get('responded', 0) for d in emails_by_date[-30:]],
                        'borderColor': '#10b981',
                        'backgroundColor': 'rgba(16, 185, 129, 0.1)',
                        'fill': True,
                        'tension': 0.4,
                        'pointRadius': 4,
                        'pointHoverRadius': 6
                    }
                ]
            }
        
        elif chart_type == 'doughnut':
            # Email status doughnut
            return {
                'type': 'doughnut',
                'title': '📬 Trạng thái email',
                'labels': ['Đã phản hồi ✅', 'Chờ phản hồi ⏳'],
                'data': [email_stats.get('responded', 0), email_stats.get('pending', 0)],
                'colors': ['#10b981', '#f59e0b']
            }
        
        elif chart_type == 'cv':
            # CV score distribution
            score_dist = cv_stats.get('score_distribution', {})
            return {
                'type': 'bar',
                'title': '📋 Phân bố điểm đánh giá CV',
                'labels': list(score_dist.keys()) if score_dist else ['0-40%', '40-60%', '60-80%', '80-100%'],
                'datasets': [{
                    'label': 'Số lượng CV',
                    'data': list(score_dist.values()) if score_dist else [0, 0, 0, 0],
                    'backgroundColor': [
                        'rgba(239, 68, 68, 0.8)',   # Red - low
                        'rgba(245, 158, 11, 0.8)',  # Orange - medium
                        'rgba(59, 130, 246, 0.8)',  # Blue - good
                        'rgba(16, 185, 129, 0.8)'   # Green - excellent
                    ],
                    'borderColor': ['#ef4444', '#f59e0b', '#3b82f6', '#10b981'],
                    'borderWidth': 2,
                    'borderRadius': 8
                }]
            }
        
        elif chart_type == 'decision':
            # Decision analysis
            decisions = email_stats.get('decisions', {})
            return {
                'type': 'polarArea',
                'title': '🎯 Phân tích quyết định từ phản hồi',
                'labels': ['Đồng ý ✅', 'Từ chối ❌', 'Chưa quyết định 🤔', 'Cần thêm thông tin ℹ️'],
                'data': [
                    decisions.get('agreed', 0),
                    decisions.get('disagreed', 0),
                    decisions.get('undecided', 0),
                    decisions.get('needs_more_info', 0)
                ],
                'colors': ['#10b981', '#ef4444', '#f59e0b', '#3b82f6']
            }
        
        elif chart_type == 'cv_qualified':
            # CV qualification pie
            return {
                'type': 'pie',
                'title': '👥 Tỷ lệ ứng viên đạt yêu cầu',
                'labels': ['Đạt yêu cầu (≥85%) ✅', 'Chưa đạt ❌'],
                'data': [cv_stats.get('qualified', 0), cv_stats.get('not_qualified', 0)],
                'colors': ['#10b981', '#ef4444']
            }
        
        elif chart_type == 'user_stats':
            # User statistics (admin only) - overview
            if is_admin:
                user_stats = self._get_user_statistics_admin()
                return {
                    'type': 'doughnut',
                    'title': '👥 Phân bổ người dùng hệ thống',
                    'labels': ['Admin 👑', 'User hoạt động 👤', 'User không hoạt động ⏸️'],
                    'data': [
                        user_stats.get('admin_count', 0),
                        user_stats.get('active_users', 0) - user_stats.get('admin_count', 0),
                        user_stats.get('inactive_count', 0)
                    ],
                    'colors': ['#8b5cf6', '#10b981', '#94a3b8']
                }
            else:
                return {
                    'type': 'doughnut',
                    'title': '⚠️ Không có quyền xem',
                    'labels': ['Bạn cần quyền Admin để xem thống kê người dùng'],
                    'data': [1],
                    'colors': ['#94a3b8']
                }
        
        elif chart_type == 'user_activity':
            # User activity breakdown (admin only)
            if is_admin:
                user_stats = self._get_user_statistics_admin()
                top_users = user_stats.get('top_active_users', [])[:7]
                
                if not top_users:
                    return {
                        'type': 'bar',
                        'title': '📊 Hoạt động người dùng',
                        'labels': ['Chưa có dữ liệu'],
                        'datasets': [{'label': 'Hoạt động', 'data': [0], 'backgroundColor': '#94a3b8'}]
                    }
                
                return {
                    'type': 'bar',
                    'title': '📊 Top hoạt động người dùng',
                    'labels': [u.get('name', 'User')[:15] for u in top_users],
                    'datasets': [
                        {
                            'label': 'Email đã gửi',
                            'data': [u.get('email_count', 0) for u in top_users],
                            'backgroundColor': 'rgba(99, 102, 241, 0.8)',
                            'borderColor': '#6366f1',
                            'borderWidth': 2,
                            'borderRadius': 6
                        },
                        {
                            'label': 'CV đã đánh giá',
                            'data': [u.get('cv_count', 0) for u in top_users],
                            'backgroundColor': 'rgba(16, 185, 129, 0.8)',
                            'borderColor': '#10b981',
                            'borderWidth': 2,
                            'borderRadius': 6
                        }
                    ]
                }
            else:
                return {
                    'type': 'bar',
                    'title': '⚠️ Không có quyền xem',
                    'labels': ['Admin only'],
                    'datasets': [{'label': '', 'data': [0], 'backgroundColor': '#94a3b8'}]
                }
        
        elif chart_type == 'radar':
            # Overall performance radar
            total_emails = email_stats.get('total_sent', 0) or 1
            total_cv = cv_stats.get('total', 0) or 1
            
            return {
                'type': 'radar',
                'title': '📊 Tổng quan hiệu suất',
                'labels': ['Tỷ lệ phản hồi', 'Phản hồi tích cực', 'Tỷ lệ CV đạt', 'Email thành công', 'Đánh giá CV'],
                'datasets': [{
                    'label': 'Hiệu suất (%)',
                    'data': [
                        email_stats.get('response_rate', 0),
                        (email_stats.get('sentiments', {}).get('positive', 0) / max(email_stats.get('responded', 1), 1)) * 100,
                        cv_stats.get('qualification_rate', 0),
                        min((email_stats.get('responded', 0) / total_emails) * 100, 100),
                        min((cv_stats.get('qualified', 0) / total_cv) * 100, 100)
                    ],
                    'backgroundColor': 'rgba(99, 102, 241, 0.2)',
                    'borderColor': '#6366f1',
                    'pointBackgroundColor': '#6366f1',
                    'pointBorderColor': '#fff',
                    'pointHoverBackgroundColor': '#fff',
                    'pointHoverBorderColor': '#6366f1'
                }]
            }
        
        elif chart_type == 'horizontalBar':
            # Horizontal bar for ranking
            top_recipients = email_stats.get('top_recipients', [])[:8]
            return {
                'type': 'horizontalBar',
                'title': '🏆 Xếp hạng người nhận email',
                'labels': [r.get('name', r.get('email', '?'))[:20] for r in top_recipients] or ['Chưa có dữ liệu'],
                'datasets': [{
                    'label': 'Số email',
                    'data': [r.get('count', 0) for r in top_recipients] or [0],
                    'backgroundColor': [
                        '#6366f1', '#8b5cf6', '#a855f7', '#d946ef',
                        '#ec4899', '#f43f5e', '#f97316', '#eab308'
                    ][:len(top_recipients) or 1]
                }]
            }
        
        elif chart_type == 'stats_cards':
            # Stats cards - special type for card display
            return {
                'type': 'stats_cards',
                'title': '📊 Tổng quan thống kê',
                'cards': [
                    {
                        'icon': '📧',
                        'label': 'Email đã gửi',
                        'value': email_stats.get('total_sent', 0),
                        'color': '#6366f1',
                        'trend': f"+{email_stats.get('responded', 0)} phản hồi"
                    },
                    {
                        'icon': '✅',
                        'label': 'Đã phản hồi',
                        'value': email_stats.get('responded', 0),
                        'color': '#10b981',
                        'percent': email_stats.get('response_rate', 0)
                    },
                    {
                        'icon': '⏳',
                        'label': 'Chờ phản hồi',
                        'value': email_stats.get('pending', 0),
                        'color': '#f59e0b'
                    },
                    {
                        'icon': '📋',
                        'label': 'CV đã đánh giá',
                        'value': cv_stats.get('total', 0),
                        'color': '#8b5cf6',
                        'trend': f"{cv_stats.get('qualified', 0)} đạt yêu cầu"
                    }
                ]
            }
        
        elif chart_type == 'progress':
            # Progress bars
            total_sent = email_stats.get('total_sent', 0) or 1
            total_cv = cv_stats.get('total', 0) or 1
            return {
                'type': 'progress',
                'title': '📈 Tiến độ hoạt động',
                'items': [
                    {
                        'label': 'Tỷ lệ phản hồi email',
                        'value': email_stats.get('responded', 0),
                        'max': total_sent,
                        'percent': round(email_stats.get('response_rate', 0), 1),
                        'color': '#10b981'
                    },
                    {
                        'label': 'Phản hồi tích cực',
                        'value': email_stats.get('sentiments', {}).get('positive', 0),
                        'max': email_stats.get('responded', 0) or 1,
                        'percent': round((email_stats.get('sentiments', {}).get('positive', 0) / max(email_stats.get('responded', 1), 1)) * 100, 1),
                        'color': '#6366f1'
                    },
                    {
                        'label': 'CV đạt yêu cầu',
                        'value': cv_stats.get('qualified', 0),
                        'max': total_cv,
                        'percent': round(cv_stats.get('qualification_rate', 0), 1),
                        'color': '#8b5cf6'
                    },
                    {
                        'label': 'Email mời phỏng vấn',
                        'value': cv_stats.get('emails_sent', 0),
                        'max': cv_stats.get('qualified', 0) or 1,
                        'percent': round((cv_stats.get('emails_sent', 0) / max(cv_stats.get('qualified', 1), 1)) * 100, 1),
                        'color': '#f59e0b'
                    }
                ]
            }
        
        elif chart_type == 'table_email':
            # Email comparison table
            top_recipients = email_stats.get('top_recipients', [])[:10]
            return {
                'type': 'table',
                'title': '📊 Bảng thống kê email theo người nhận',
                'headers': ['#', 'Người nhận', 'Đã gửi', 'Phản hồi', 'Tỷ lệ'],
                'rows': [
                    [
                        i + 1,
                        r.get('name', r.get('email', '?'))[:25],
                        r.get('count', 0),
                        r.get('responded', 0),
                        f"{round((r.get('responded', 0) / max(r.get('count', 1), 1)) * 100)}%"
                    ] for i, r in enumerate(top_recipients)
                ] or [['', 'Chưa có dữ liệu', '', '', '']]
            }
        
        elif chart_type == 'table_cv':
            # CV score table
            score_dist = cv_stats.get('score_distribution', {})
            return {
                'type': 'table',
                'title': '📋 Bảng phân bố điểm CV',
                'headers': ['Khoảng điểm', 'Số lượng', 'Đánh giá', 'Tỷ lệ'],
                'rows': [
                    ['0-50%', score_dist.get('0-50', 0), '❌ Chưa đạt', f"{round(score_dist.get('0-50', 0) / max(cv_stats.get('total', 1), 1) * 100)}%"],
                    ['51-70%', score_dist.get('51-70', 0), '⚠️ Trung bình', f"{round(score_dist.get('51-70', 0) / max(cv_stats.get('total', 1), 1) * 100)}%"],
                    ['71-84%', score_dist.get('71-84', 0), '✅ Khá', f"{round(score_dist.get('71-84', 0) / max(cv_stats.get('total', 1), 1) * 100)}%"],
                    ['85-100%', score_dist.get('85-100', 0), '🌟 Xuất sắc', f"{round(score_dist.get('85-100', 0) / max(cv_stats.get('total', 1), 1) * 100)}%"]
                ]
            }
        
        elif chart_type == 'table_users':
            # Users table (admin only)
            if is_admin:
                user_stats = self._get_user_statistics_admin()
                top_users = user_stats.get('top_active_users', [])[:10]
                return {
                    'type': 'table',
                    'title': '👥 Bảng hoạt động người dùng',
                    'headers': ['#', 'Tên', 'Vai trò', 'Email gửi', 'CV đánh giá', 'Tổng'],
                    'rows': [
                        [
                            i + 1,
                            u.get('name', '?')[:20],
                            '👑 Admin' if u.get('role') == 'admin' else '👤 User',
                            u.get('email_count', 0),
                            u.get('cv_count', 0),
                            u.get('total_activity', 0)
                        ] for i, u in enumerate(top_users)
                    ] or [['', 'Chưa có dữ liệu', '', '', '', '']]
                }
            else:
                return {
                    'type': 'table',
                    'title': '⚠️ Không có quyền',
                    'headers': ['Thông báo'],
                    'rows': [['Bạn cần quyền Admin để xem']]
                }
        
        elif chart_type == 'comparison':
            # Comparison view
            return {
                'type': 'comparison',
                'title': '⚖️ So sánh Email vs CV',
                'items': [
                    {
                        'label': 'Email',
                        'icon': '📧',
                        'stats': [
                            {'name': 'Tổng số', 'value': email_stats.get('total_sent', 0)},
                            {'name': 'Thành công', 'value': email_stats.get('responded', 0)},
                            {'name': 'Tỷ lệ', 'value': f"{email_stats.get('response_rate', 0)}%"}
                        ],
                        'color': '#6366f1'
                    },
                    {
                        'label': 'CV',
                        'icon': '📋',
                        'stats': [
                            {'name': 'Tổng số', 'value': cv_stats.get('total', 0)},
                            {'name': 'Đạt yêu cầu', 'value': cv_stats.get('qualified', 0)},
                            {'name': 'Tỷ lệ', 'value': f"{cv_stats.get('qualification_rate', 0)}%"}
                        ],
                        'color': '#10b981'
                    }
                ]
            }
        
        else:  # overview - email status doughnut
            return {
                'type': 'doughnut',
                'title': '📬 Tổng quan trạng thái email',
                'labels': ['Đã phản hồi ✅', 'Chờ phản hồi ⏳'],
                'data': [email_stats.get('responded', 0), email_stats.get('pending', 0)],
                'colors': ['#10b981', '#f59e0b']
            }
