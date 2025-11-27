"""
CV Evaluator Service - Đánh giá CV ứng viên sử dụng Azure OpenAI
"""
from openai import AzureOpenAI
from typing import Dict, Optional, List
import logging
import json
import re

from config.settings import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_DEPLOYMENT_NAME,
    AZURE_OPENAI_API_VERSION
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CVEvaluator:
    """Service đánh giá CV ứng viên"""
    
    def __init__(self):
        self.client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
            api_version=AZURE_OPENAI_API_VERSION
        )
        self.deployment_name = AZURE_OPENAI_DEPLOYMENT_NAME
        
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
        system_prompt = """Bạn là chuyên gia tuyển dụng (HR Expert) có kinh nghiệm đánh giá CV ứng viên.
Nhiệm vụ của bạn là phân tích CV và so sánh với yêu cầu công việc để đưa ra đánh giá chi tiết.

Hãy đánh giá theo các tiêu chí sau:
1. Kỹ năng kỹ thuật (Technical Skills) - 30%
2. Kinh nghiệm làm việc (Experience) - 25%
3. Học vấn/Chứng chỉ (Education/Certifications) - 20%
4. Kỹ năng mềm (Soft Skills) - 15%
5. Độ phù hợp tổng thể (Overall Fit) - 10%

Trả về kết quả bằng TIẾNG VIỆT dưới dạng JSON với cấu trúc sau:
{
    "overall_score": 0-100,
    "is_qualified": true/false,
    "scores": {
        "technical_skills": {"score": 0-100, "comment": "nhận xét"},
        "experience": {"score": 0-100, "comment": "nhận xét"},
        "education": {"score": 0-100, "comment": "nhận xét"},
        "soft_skills": {"score": 0-100, "comment": "nhận xét"},
        "overall_fit": {"score": 0-100, "comment": "nhận xét"}
    },
    "strengths": ["điểm mạnh 1", "điểm mạnh 2"],
    "weaknesses": ["điểm yếu 1", "điểm yếu 2"],
    "missing_requirements": ["yêu cầu thiếu 1", "yêu cầu thiếu 2"],
    "recommendation": "Khuyến nghị chi tiết",
    "summary": "Tóm tắt ngắn gọn về ứng viên"
}

Lưu ý: is_qualified = true nếu overall_score >= 85"""

        user_prompt = f"""Hãy đánh giá CV sau đây cho vị trí: {job_title}
{f'Công ty: {company_name}' if company_name else ''}

=== YÊU CẦU CÔNG VIỆC ===
{job_requirements}

=== NỘI DUNG CV ỨNG VIÊN ===
{cv_content}

Hãy đánh giá chi tiết và cho điểm từ 0-100. Ứng viên được coi là PHÙ HỢP nếu điểm >= 85."""

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
            
            # Đảm bảo is_qualified dựa trên overall_score
            result['is_qualified'] = result.get('overall_score', 0) >= 80
            
            logger.info(f"CV evaluated: Score={result.get('overall_score', 0)}, Qualified={result.get('is_qualified', False)}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to evaluate CV: {str(e)}")
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
        
        Args:
            candidate_name: Tên ứng viên
            candidate_email: Email ứng viên
            job_title: Vị trí tuyển dụng
            company_name: Tên công ty
            evaluation_result: Kết quả đánh giá CV
            interview_details: Thông tin về buổi phỏng vấn (tùy chọn)
            
        Returns:
            Dictionary với 'subject' và 'body'
        """
        system_prompt = """Bạn là chuyên gia HR viết email mời phỏng vấn bằng tiếng Việt.
Tạo email chuyên nghiệp, thân thiện để mời ứng viên tham gia phỏng vấn.

Email cần:
1. Chúc mừng ứng viên đã vượt qua vòng đánh giá CV
2. Giới thiệu ngắn gọn về công ty và vị trí
3. Mời ứng viên tham gia phỏng vấn
4. Nêu các bước tiếp theo
5. Thể hiện sự chuyên nghiệp và thân thiện

Trả về JSON với 'subject' và 'body'."""

        strengths = evaluation_result.get('strengths', [])
        strengths_text = ', '.join(strengths[:3]) if strengths else 'nhiều điểm nổi bật'
        
        user_prompt = f"""Tạo email mời phỏng vấn bằng tiếng Việt:

Ứng viên: {candidate_name}
Email: {candidate_email}
Vị trí: {job_title}
Công ty: {company_name}
Điểm đánh giá CV: {evaluation_result.get('overall_score', 0)}/100
Điểm mạnh của ứng viên: {strengths_text}
{f'Thông tin phỏng vấn: {interview_details}' if interview_details else 'Thời gian phỏng vấn sẽ được thống nhất qua email'}

Tạo email chuyên nghiệp, ấn tượng để mời ứng viên phỏng vấn."""

        try:
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.6,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            logger.info("Interview invitation email generated successfully")
            return result
            
        except Exception as e:
            logger.error(f"Failed to generate invitation: {str(e)}")
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
        system_prompt = """Bạn là chuyên gia HR viết email từ chối lịch sự bằng tiếng Việt.
Email cần:
1. Cảm ơn ứng viên đã quan tâm
2. Thông báo kết quả một cách tế nhị
3. Khuyến khích ứng viên cho các cơ hội tương lai
4. Giữ mối quan hệ tốt đẹp

Trả về JSON với 'subject' và 'body'."""

        user_prompt = f"""Tạo email từ chối lịch sự bằng tiếng Việt:

Ứng viên: {candidate_name}
Vị trí: {job_title}
Công ty: {company_name}
Điểm đánh giá: {evaluation_result.get('overall_score', 0)}/100

Tạo email từ chối nhẹ nhàng, chuyên nghiệp và khuyến khích ứng viên."""

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
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logger.error(f"Failed to generate rejection email: {str(e)}")
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


def extract_text_from_file(file_path: str) -> str:
    """
    Trích xuất text từ file CV (hỗ trợ .txt, .pdf, .docx)
    """
    import os
    ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
                
        elif ext == '.pdf':
            try:
                import PyPDF2
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                    return text
            except ImportError:
                logger.warning("PyPDF2 not installed. Install with: pip install PyPDF2")
                return ""
                
        elif ext in ['.docx', '.doc']:
            try:
                import docx
                doc = docx.Document(file_path)
                return "\n".join([para.text for para in doc.paragraphs])
            except ImportError:
                logger.warning("python-docx not installed. Install with: pip install python-docx")
                return ""
                
        else:
            logger.warning(f"Unsupported file type: {ext}")
            return ""
            
    except Exception as e:
        logger.error(f"Failed to extract text from {file_path}: {str(e)}")
        return ""
