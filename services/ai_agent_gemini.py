"""
AI Agent Service - Uses Google Gemini API to generate emails and analyze responses
Phiên bản sử dụng Gemini thay vì Azure OpenAI
"""
import google.generativeai as genai
from typing import Dict, Optional
import logging
import json
import re

from config.settings import GEMINI_API_KEY, GEMINI_MODEL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AIAgentGemini:
    """AI Agent for email generation and response analysis using Google Gemini"""
    
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config={
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
            }
        )
        
    def _extract_json(self, text: str) -> Dict:
        """Extract JSON from response text"""
        # Try to find JSON in the response
        try:
            # First try direct parse
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON block in markdown
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON object pattern
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        logger.error(f"Could not parse JSON from: {text[:500]}")
        return {}
        
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
        
        prompt = f"""You are a professional email writing assistant. Your task is to compose clear, effective emails in {lang_info['name']}.

When writing the email:
1. {lang_info['greeting']}
2. Be concise but complete with information
3. Match the requested tone
4. Include all necessary information
5. Easy to read and reply to
6. {lang_info['write_in']}

Write an email in {lang_info['name']} with the following information:

Sender: {sender_name}
Recipient: {recipient_name} ({recipient_email})
Purpose: {purpose}
Tone: {tone_text}
{f'Additional information: {additional_context}' if additional_context else ''}

Create a complete email in {lang_info['name']} with appropriate subject and body.

Return the result EXACTLY in JSON format as follows (no other text):
{{"subject": "Email subject in {lang_info['name']}", "body": "Email body in {lang_info['name']}"}}"""

        try:
            response = self.model.generate_content(prompt)
            result = self._extract_json(response.text)
            
            if 'subject' in result and 'body' in result:
                logger.info("Email generated successfully with Gemini")
                return result
            else:
                logger.warning("Invalid response format from Gemini")
                return {
                    "subject": "Email",
                    "body": response.text
                }
            
        except Exception as e:
            logger.error(f"Failed to generate email with Gemini: {str(e)}")
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
        """
        prompt = f"""Bạn là chuyên gia phân tích email phản hồi. Nhiệm vụ của bạn là phân tích các email phản hồi và xác định:
1. Cảm xúc của phản hồi (tích cực, tiêu cực, trung tính)
2. Người nhận đồng ý, không đồng ý, hay chưa quyết định
3. Các điểm chính trong phản hồi
4. Các hành động cần thực hiện tiếp theo
5. Tóm tắt ý kiến/quan điểm của họ

Hãy phân tích email phản hồi sau đây:

EMAIL GỐC:
Tiêu đề: {original_email_subject}
Mục đích: {original_purpose}
Nội dung:
{original_email_body}

PHẢN HỒI TỪ NGƯỜI NHẬN:
Tiêu đề: {response_subject}
Nội dung:
{response_body}

Phân tích phản hồi này và đưa ra đánh giá chi tiết về quan điểm và cảm xúc của người nhận.

Trả về kết quả phân tích bằng TIẾNG VIỆT CHÍNH XÁC dưới dạng JSON với cấu trúc sau (không có text khác):
{{
    "sentiment": "tích cực|tiêu cực|trung tính",
    "decision": "đồng ý|không đồng ý|chưa quyết định|cần thêm thông tin",
    "confidence_score": 0.0-1.0,
    "key_points": ["điểm 1", "điểm 2"],
    "action_items": ["hành động 1", "hành động 2"],
    "summary": "Tóm tắt ngắn gọn phản hồi bằng tiếng Việt",
    "full_analysis": "Phân tích chi tiết phản hồi bằng tiếng Việt"
}}"""

        try:
            response = self.model.generate_content(prompt)
            result = self._extract_json(response.text)
            
            if result:
                logger.info("Response analyzed successfully with Gemini")
                return result
            else:
                return {
                    "sentiment": "unknown",
                    "decision": "error",
                    "summary": "Không thể phân tích phản hồi"
                }
            
        except Exception as e:
            logger.error(f"Failed to analyze response with Gemini: {str(e)}")
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
        """
        prompt = f"""Bạn là trợ lý tạo email thông báo bằng tiếng Việt để thông báo cho người dùng về các phản hồi email. Tạo thông báo rõ ràng, đầy đủ thông tin gồm:
1. Ai đã phản hồi
2. Quyết định/cảm xúc của họ
3. Các điểm chính trong phản hồi
4. Các hành động cần thực hiện tiếp theo

Tạo email thông báo bằng tiếng Việt cho {sender_name} về phản hồi nhận được từ {recipient_name}.

Mục đích ban đầu: {original_purpose}

Kết quả phân tích phản hồi:
- Cảm xúc: {analysis.get('sentiment', 'chưa xác định')}
- Quyết định: {analysis.get('decision', 'chưa xác định')}
- Độ tin cậy: {analysis.get('confidence_score', 'N/A')}
- Điểm chính: {', '.join(analysis.get('key_points', []))}
- Hành động cần làm: {', '.join(analysis.get('action_items', []))}
- Tóm tắt: {analysis.get('summary', 'Không có tóm tắt')}
- Phân tích chi tiết: {analysis.get('full_analysis', '')}

Tạo email thông báo thân thiện và đầy đủ thông tin bằng TIẾNG VIỆT.

Trả về kết quả CHÍNH XÁC dưới dạng JSON với format sau (không có text khác):
{{"subject": "Tiêu đề email", "body": "Nội dung email"}}"""

        try:
            response = self.model.generate_content(prompt)
            result = self._extract_json(response.text)
            
            if 'subject' in result and 'body' in result:
                logger.info("Notification email generated successfully with Gemini")
                return result
            else:
                return {
                    "subject": f"Phản hồi từ {recipient_name}",
                    "body": f"Đã nhận được phản hồi. Tóm tắt: {analysis.get('summary', 'Không thể phân tích')}"
                }
            
        except Exception as e:
            logger.error(f"Failed to generate notification with Gemini: {str(e)}")
            return {
                "subject": f"Phản hồi từ {recipient_name}",
                "body": f"Đã nhận được phản hồi. Tóm tắt: {analysis.get('summary', 'Không thể phân tích')}"
            }
