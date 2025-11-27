"""
CV Evaluator Service - Đánh giá CV ứng viên sử dụng Google Gemini API
Phiên bản sử dụng Gemini thay vì Azure OpenAI
"""
import google.generativeai as genai
from typing import Dict, Optional, List
import logging
import json
import re

from config.settings import GEMINI_API_KEY, GEMINI_MODEL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CVEvaluatorGemini:
    """Service đánh giá CV ứng viên sử dụng Google Gemini"""
    
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config={
                "temperature": 0.3,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
            }
        )
        
    def _extract_json(self, text: str) -> Dict:
        """Extract JSON from response text"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        logger.error(f"Could not parse JSON from: {text[:500]}")
        return {}
        
    def evaluate_cv(
        self,
        cv_content: str,
        job_title: str,
        job_requirements: str,
        company_name: Optional[str] = None
    ) -> Dict:
        """
        Đánh giá CV của ứng viên so với yêu cầu công việc
        
        Args:
            cv_content: Nội dung CV (text)
            job_title: Tên vị trí tuyển dụng
            job_requirements: Yêu cầu công việc chi tiết
            company_name: Tên công ty (tùy chọn)
            
        Returns:
            Dictionary chứa kết quả đánh giá
        """
        prompt = f"""Bạn là chuyên gia tuyển dụng (HR Expert) có kinh nghiệm đánh giá CV ứng viên.
Nhiệm vụ của bạn là phân tích CV và so sánh với yêu cầu công việc để đưa ra đánh giá chi tiết.

Hãy đánh giá theo các tiêu chí sau:
1. Kỹ năng kỹ thuật (Technical Skills) - 30%
2. Kinh nghiệm làm việc (Experience) - 25%
3. Học vấn/Chứng chỉ (Education/Certifications) - 20%
4. Kỹ năng mềm (Soft Skills) - 15%
5. Độ phù hợp tổng thể (Overall Fit) - 10%

Hãy đánh giá CV sau đây cho vị trí: {job_title}
{f'Công ty: {company_name}' if company_name else ''}

=== YÊU CẦU CÔNG VIỆC ===
{job_requirements}

=== NỘI DUNG CV ỨNG VIÊN ===
{cv_content}

Hãy đánh giá chi tiết và cho điểm từ 0-100. Ứng viên được coi là PHÙ HỢP nếu điểm >= 85.

Trả về kết quả bằng TIẾNG VIỆT CHÍNH XÁC dưới dạng JSON với cấu trúc sau (không có text khác):
{{
    "overall_score": 0-100,
    "is_qualified": true/false,
    "technical_skills": 0-30,
    "experience": 0-25,
    "education": 0-20,
    "soft_skills": 0-15,
    "overall_fit": 0-10,
    "strengths": ["điểm mạnh 1", "điểm mạnh 2"],
    "weaknesses": ["điểm yếu 1", "điểm yếu 2"],
    "missing_requirements": ["yêu cầu thiếu 1", "yêu cầu thiếu 2"],
    "recommendation": "Khuyến nghị chi tiết",
    "summary": "Tóm tắt ngắn gọn về ứng viên"
}}

Lưu ý: is_qualified = true nếu overall_score >= 85"""

        try:
            response = self.model.generate_content(prompt)
            result = self._extract_json(response.text)
            
            if result:
                # Đảm bảo is_qualified dựa trên overall_score
                result['is_qualified'] = result.get('overall_score', 0) >= 85
                logger.info(f"CV evaluated with Gemini: Score={result.get('overall_score', 0)}, Qualified={result.get('is_qualified', False)}")
                return result
            else:
                return {
                    "overall_score": 0,
                    "is_qualified": False,
                    "error": "Không thể parse kết quả",
                    "summary": "Lỗi khi đánh giá CV"
                }
            
        except Exception as e:
            logger.error(f"Failed to evaluate CV with Gemini: {str(e)}")
            return {
                "overall_score": 0,
                "is_qualified": False,
                "error": str(e),
                "summary": f"Lỗi khi đánh giá CV: {str(e)}"
            }
    
    def generate_interview_invitation(
        self,
        candidate_name: str,
        candidate_email: str,
        job_title: str,
        company_name: str,
        evaluation_result: Dict,
        interview_details: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Tạo email mời phỏng vấn cho ứng viên đạt yêu cầu
        """
        strengths = evaluation_result.get('strengths', [])
        strengths_text = ', '.join(strengths[:3]) if strengths else 'nhiều điểm nổi bật'
        
        prompt = f"""Bạn là chuyên gia HR viết email mời phỏng vấn bằng tiếng Việt.
Tạo email chuyên nghiệp, thân thiện để mời ứng viên tham gia phỏng vấn.

Email cần:
1. Chúc mừng ứng viên đã vượt qua vòng đánh giá CV
2. Giới thiệu ngắn gọn về công ty và vị trí
3. Mời ứng viên tham gia phỏng vấn
4. Nêu các bước tiếp theo
5. Thể hiện sự chuyên nghiệp và thân thiện

Tạo email mời phỏng vấn bằng tiếng Việt:

Ứng viên: {candidate_name}
Email: {candidate_email}
Vị trí: {job_title}
Công ty: {company_name}
Điểm đánh giá CV: {evaluation_result.get('overall_score', 0)}/100
Điểm mạnh của ứng viên: {strengths_text}
{f'Thông tin phỏng vấn: {interview_details}' if interview_details else 'Thời gian phỏng vấn sẽ được thống nhất qua email'}

Tạo email chuyên nghiệp, ấn tượng để mời ứng viên phỏng vấn.

Trả về CHÍNH XÁC dưới dạng JSON với format sau (không có text khác):
{{"subject": "Tiêu đề email", "body": "Nội dung email"}}"""

        try:
            response = self.model.generate_content(prompt)
            result = self._extract_json(response.text)
            
            if 'subject' in result and 'body' in result:
                logger.info("Interview invitation email generated successfully with Gemini")
                return result
            else:
                return self._default_invitation(candidate_name, job_title, company_name)
            
        except Exception as e:
            logger.error(f"Failed to generate invitation with Gemini: {str(e)}")
            return self._default_invitation(candidate_name, job_title, company_name)
    
    def _default_invitation(self, candidate_name: str, job_title: str, company_name: str) -> Dict[str, str]:
        return {
            "subject": f"Thư mời phỏng vấn - Vị trí {job_title} tại {company_name}",
            "body": f"""Kính gửi {candidate_name},

Chúng tôi rất vui thông báo rằng hồ sơ của bạn đã vượt qua vòng đánh giá CV cho vị trí {job_title} tại {company_name}.

Chúng tôi muốn mời bạn tham gia buổi phỏng vấn. Vui lòng phản hồi email này để chúng tôi sắp xếp thời gian phù hợp.

Trân trọng,
Phòng Nhân sự {company_name}"""
        }
    
    def generate_rejection_email(
        self,
        candidate_name: str,
        job_title: str,
        company_name: str,
        evaluation_result: Dict
    ) -> Dict[str, str]:
        """
        Tạo email từ chối lịch sự cho ứng viên không đạt yêu cầu
        """
        prompt = f"""Bạn là chuyên gia HR viết email từ chối lịch sự bằng tiếng Việt.
Email cần:
1. Cảm ơn ứng viên đã quan tâm
2. Thông báo kết quả một cách tế nhị
3. Khuyến khích ứng viên cho các cơ hội tương lai
4. Giữ mối quan hệ tốt đẹp

Tạo email từ chối lịch sự bằng tiếng Việt:

Ứng viên: {candidate_name}
Vị trí: {job_title}
Công ty: {company_name}
Điểm đánh giá: {evaluation_result.get('overall_score', 0)}/100

Tạo email từ chối nhẹ nhàng, chuyên nghiệp và khuyến khích ứng viên.

Trả về CHÍNH XÁC dưới dạng JSON với format sau (không có text khác):
{{"subject": "Tiêu đề email", "body": "Nội dung email"}}"""

        try:
            response = self.model.generate_content(prompt)
            result = self._extract_json(response.text)
            
            if 'subject' in result and 'body' in result:
                return result
            else:
                return self._default_rejection(candidate_name, job_title, company_name)
            
        except Exception as e:
            logger.error(f"Failed to generate rejection email with Gemini: {str(e)}")
            return self._default_rejection(candidate_name, job_title, company_name)
    
    def _default_rejection(self, candidate_name: str, job_title: str, company_name: str) -> Dict[str, str]:
        return {
            "subject": f"Kết quả ứng tuyển - Vị trí {job_title}",
            "body": f"""Kính gửi {candidate_name},

Cảm ơn bạn đã quan tâm đến vị trí {job_title} tại {company_name}.

Sau khi xem xét kỹ lưỡng, chúng tôi nhận thấy hồ sơ của bạn chưa hoàn toàn phù hợp với yêu cầu hiện tại.

Chúng tôi khuyến khích bạn theo dõi các cơ hội tuyển dụng khác của công ty trong tương lai.

Chúc bạn thành công!

Trân trọng,
Phòng Nhân sự {company_name}"""
        }
