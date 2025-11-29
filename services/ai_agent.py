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
        language: str = "vi",
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
            language: Language code (vi, en, ja, zh, ko, fr)
            additional_context: Any additional context for the email
            
        Returns:
            Dictionary with 'subject' and 'body' keys
        """
        # Tone mapping for different languages
        tone_map = {
            'vi': {
                'professional': 'chuyên nghiệp, lịch sự',
                'friendly': 'thân thiện, gần gũi',
                'formal': 'trang trọng, nghiêm túc',
                'casual': 'thường ngày, thoải mái'
            },
            'en': {
                'professional': 'professional and polite',
                'friendly': 'friendly and warm',
                'formal': 'formal and serious',
                'casual': 'casual and relaxed'
            },
            'ja': {
                'professional': 'プロフェッショナルで丁寧',
                'friendly': 'フレンドリーで親しみやすい',
                'formal': 'フォーマルで真剣',
                'casual': 'カジュアルでリラックス'
            },
            'zh': {
                'professional': '专业且礼貌',
                'friendly': '友好且亲切',
                'formal': '正式且严肃',
                'casual': '随意且轻松'
            },
            'ko': {
                'professional': '전문적이고 예의 바른',
                'friendly': '친근하고 따뜻한',
                'formal': '격식 있고 진지한',
                'casual': '캐주얼하고 편안한'
            },
            'fr': {
                'professional': 'professionnel et poli',
                'friendly': 'amical et chaleureux',
                'formal': 'formel et sérieux',
                'casual': 'décontracté et détendu'
            }
        }
        
        # Language instructions
        language_instructions = {
            'vi': {
                'name': 'tiếng Việt',
                'greeting': 'Sử dụng lời chào và kết thúc phù hợp với văn hóa Việt Nam',
                'write_in': 'LUÔN LUÔN viết bằng tiếng Việt'
            },
            'en': {
                'name': 'English',
                'greeting': 'Use appropriate English greetings and closings',
                'write_in': 'ALWAYS write in English'
            },
            'ja': {
                'name': '日本語',
                'greeting': '日本のビジネス文化に適した挨拶と締めくくりを使用してください',
                'write_in': '必ず日本語で書いてください'
            },
            'zh': {
                'name': '中文',
                'greeting': '使用符合中国文化的问候语和结束语',
                'write_in': '始终使用中文写作'
            },
            'ko': {
                'name': '한국어',
                'greeting': '한국 비즈니스 문화에 적합한 인사말과 맺음말을 사용하세요',
                'write_in': '항상 한국어로 작성하세요'
            },
            'fr': {
                'name': 'français',
                'greeting': 'Utilisez des salutations et formules de politesse appropriées à la culture française',
                'write_in': 'Écrivez TOUJOURS en français'
            }
        }
        
        lang = language if language in language_instructions else 'vi'
        lang_info = language_instructions[lang]
        tone_text = tone_map.get(lang, tone_map['en']).get(tone, 'professional')
        
        system_prompt = f"""You are a professional email writing assistant. Your task is to compose clear, effective emails in {lang_info['name']}.

When writing the email:
1. {lang_info['greeting']}
2. Be concise but complete with information
3. Match the requested tone
4. Include all necessary information
5. Easy to read and reply to
6. {lang_info['write_in']}

Return the result in JSON format with keys 'subject' and 'body'."""

        user_prompt = f"""Write an email in {lang_info['name']} with the following information:

Sender: {sender_name}
Recipient: {recipient_name} ({recipient_email})
Purpose: {purpose}
Tone: {tone_text}
{f'Additional information: {additional_context}' if additional_context else ''}

Create a complete email in {lang_info['name']} with appropriate subject and body."""

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
