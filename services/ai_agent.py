"""
AI Agent Service - Uses Azure OpenAI to generate emails and analyze responses
"""
from openai import AzureOpenAI
from typing import Dict, Optional
import logging
import json

from config.settings import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_DEPLOYMENT_NAME,
    AZURE_OPENAI_API_VERSION
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AIAgent:
    """AI Agent for email generation and response analysis"""
    
    def __init__(self):
        self.client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION
        )
        self.deployment_name = AZURE_OPENAI_DEPLOYMENT_NAME
        
    def generate_email(
        self, 
        sender_name: str,
        recipient_name: str,
        recipient_email: str,
        purpose: str,
        tone: str = "professional",
        additional_context: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Generate an email based on the user's request
        
        Args:
            sender_name: Name of person A (sender)
            recipient_name: Name of person B (recipient)
            recipient_email: Email of person B
            purpose: The purpose/request for the email
            tone: Tone of the email (professional, friendly, formal, casual)
            additional_context: Any additional context for the email
            
        Returns:
            Dictionary with 'subject' and 'body' keys
        """
        tone_map = {
            'professional': 'chuyên nghiệp, lịch sự',
            'friendly': 'thân thiện, gần gũi',
            'formal': 'trang trọng, nghiêm túc',
            'casual': 'thường ngày, thoải mái'
        }
        tone_vietnamese = tone_map.get(tone, 'chuyên nghiệp')
        
        system_prompt = """Bạn là một trợ lý viết email chuyên nghiệp bằng tiếng Việt. Nhiệm vụ của bạn là soạn email rõ ràng, hiệu quả theo yêu cầu của người dùng.

Khi viết email:
1. Sử dụng lời chào và kết thúc phù hợp với văn hóa Việt Nam
2. Ngắn gọn nhưng đầy đủ thông tin
3. Phù hợp với giọng điệu yêu cầu
4. Bao gồm tất cả thông tin cần thiết
5. Dễ đọc và dễ trả lời
6. LUÔN LUÔN viết bằng tiếng Việt

Trả về kết quả dưới dạng JSON với các key 'subject' và 'body'."""

        user_prompt = f"""Hãy viết một email bằng tiếng Việt với các thông tin sau:

Người gửi: {sender_name}
Người nhận: {recipient_name} ({recipient_email})
Mục đích: {purpose}
Giọng điệu: {tone_vietnamese}
{f'Thông tin bổ sung: {additional_context}' if additional_context else ''}

Tạo một email hoàn chỉnh bằng TIẾNG VIỆT với tiêu đề và nội dung phù hợp."""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            logger.info("Email generated successfully")
            return result
            
        except Exception as e:
            logger.error(f"Failed to generate email: {str(e)}")
            return {
                "subject": "Email",
                "body": f"[Error generating email: {str(e)}]"
            }
    
    def analyze_response(
        self,
        original_email_subject: str,
        original_email_body: str,
        original_purpose: str,
        response_body: str,
        response_subject: str
    ) -> Dict:
        """
        Analyze the response from person B and determine their sentiment/decision
        
        Args:
            original_email_subject: Subject of the original email sent to B
            original_email_body: Body of the original email sent to B
            original_purpose: The original purpose of sending the email
            response_body: The response email body from person B
            response_subject: The response email subject from person B
            
        Returns:
            Dictionary containing analysis results
        """
        system_prompt = """Bạn là chuyên gia phân tích email phản hồi. Nhiệm vụ của bạn là phân tích các email phản hồi và xác định:
1. Cảm xúc của phản hồi (tích cực, tiêu cực, trung tính)
2. Người nhận đồng ý, không đồng ý, hay chưa quyết định
3. Các điểm chính trong phản hồi
4. Các hành động cần thực hiện tiếp theo
5. Tóm tắt ý kiến/quan điểm của họ

Trả về kết quả phân tích bằng TIẾNG VIỆT dưới dạng JSON với cấu trúc sau:
{
    "sentiment": "tích cực|tiêu cực|trung tính",
    "decision": "đồng ý|không đồng ý|chưa quyết định|cần thêm thông tin",
    "confidence_score": 0.0-1.0,
    "key_points": ["điểm 1", "điểm 2"],
    "action_items": ["hành động 1", "hành động 2"],
    "summary": "Tóm tắt ngắn gọn phản hồi bằng tiếng Việt",
    "full_analysis": "Phân tích chi tiết phản hồi bằng tiếng Việt"
}"""

        user_prompt = f"""Hãy phân tích email phản hồi sau đây:

EMAIL GỐC:
Tiêu đề: {original_email_subject}
Mục đích: {original_purpose}
Nội dung:
{original_email_body}

PHẢN HỒI TỪ NGƯỜI NHẬN:
Tiêu đề: {response_subject}
Nội dung:
{response_body}

Phân tích phản hồi này và đưa ra đánh giá chi tiết về quan điểm và cảm xúc của người nhận. Trả lời bằng TIẾNG VIỆT."""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            logger.info("Response analyzed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Failed to analyze response: {str(e)}")
            return {
                "sentiment": "unknown",
                "decision": "error",
                "summary": f"Error analyzing response: {str(e)}"
            }
    
    def generate_notification_email(
        self,
        sender_name: str,
        original_purpose: str,
        recipient_name: str,
        analysis: Dict
    ) -> Dict[str, str]:
        """
        Generate a notification email to person A about person B's response
        
        Args:
            sender_name: Name of person A
            original_purpose: The original purpose of the email
            recipient_name: Name of person B
            analysis: The analysis results from analyze_response
            
        Returns:
            Dictionary with 'subject' and 'body' keys for the notification email
        """
        system_prompt = """Bạn là trợ lý tạo email thông báo bằng tiếng Việt để thông báo cho người dùng về các phản hồi email. Tạo thông báo rõ ràng, đầy đủ thông tin gồm:
1. Ai đã phản hồi
2. Quyết định/cảm xúc của họ
3. Các điểm chính trong phản hồi
4. Các hành động cần thực hiện tiếp theo

Trả về kết quả bằng TIẾNG VIỆT dưới dạng JSON với các key 'subject' và 'body'."""

        user_prompt = f"""Tạo email thông báo bằng tiếng Việt cho {sender_name} về phản hồi nhận được từ {recipient_name}.

Mục đích ban đầu: {original_purpose}

Kết quả phân tích phản hồi:
- Cảm xúc: {analysis.get('sentiment', 'chưa xác định')}
- Quyết định: {analysis.get('decision', 'chưa xác định')}
- Độ tin cậy: {analysis.get('confidence_score', 'N/A')}
- Điểm chính: {', '.join(analysis.get('key_points', []))}
- Hành động cần làm: {', '.join(analysis.get('action_items', []))}
- Tóm tắt: {analysis.get('summary', 'Không có tóm tắt')}
- Phân tích chi tiết: {analysis.get('full_analysis', '')}

Tạo email thông báo thân thiện và đầy đủ thông tin bằng TIẾNG VIỆT."""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            logger.info("Notification email generated successfully")
            return result
            
        except Exception as e:
            logger.error(f"Failed to generate notification: {str(e)}")
            return {
                "subject": f"Phản hồi từ {recipient_name}",
                "body": f"Đã nhận được phản hồi. Tóm tắt: {analysis.get('summary', 'Không thể phân tích')}"
            }
