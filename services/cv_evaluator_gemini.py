"""
CV Evaluator Service - Đánh giá CV ứng viên sử dụng Google Gemini API
Phiên bản sử dụng Gemini thay vì Azure OpenAI
Tối ưu hóa để có kết quả nhất quán và chính xác
"""
import google.generativeai as genai
from typing import Dict, Optional, List
import logging
import json
import re
import hashlib

from config.settings import GEMINI_API_KEY, GEMINI_MODEL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CVEvaluatorGemini:
    """Service đánh giá CV ứng viên sử dụng Google Gemini"""
    
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        # Temperature = 0 để có kết quả nhất quán nhất
        self.model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            generation_config={
                "temperature": 0,  # Đặt 0 để loại bỏ tính ngẫu nhiên
                "top_p": 1,        # Deterministic output
                "top_k": 1,        # Chọn token có xác suất cao nhất
                "max_output_tokens": 8192,
            }
        )
        # Cache để tránh đánh giá lại cùng một CV
        self._evaluation_cache = {}
        
    def _get_cache_key(self, cv_content: str, job_title: str, job_requirements: str) -> str:
        """Tạo cache key từ nội dung CV và yêu cầu công việc"""
        content = f"{cv_content.strip().lower()}|{job_title.strip().lower()}|{job_requirements.strip().lower()}"
        return hashlib.md5(content.encode()).hexdigest()
        
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
    
    def _normalize_cv_content(self, cv_content: str) -> str:
        """Chuẩn hóa nội dung CV để đánh giá nhất quán"""
        # Loại bỏ khoảng trắng thừa
        lines = [line.strip() for line in cv_content.split('\n') if line.strip()]
        return '\n'.join(lines)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Trích xuất các từ khóa quan trọng từ yêu cầu công việc"""
        # Các pattern phổ biến cho kỹ năng
        keywords = []
        # Tìm các từ viết hoa hoặc thuật ngữ kỹ thuật
        tech_patterns = re.findall(r'\b[A-Z][a-zA-Z+#]*\b|\b\d+\+?\s*(?:năm|year)s?\b', text)
        keywords.extend(tech_patterns)
        return list(set(keywords))
        
    def evaluate_cv(
        self,
        cv_content: str,
        job_title: str,
        job_requirements: str,
        company_name: Optional[str] = None
    ) -> Dict:
        """
        Đánh giá CV của ứng viên so với yêu cầu công việc
        Sử dụng hệ thống chấm điểm chi tiết với rubric cụ thể
        
        Args:
            cv_content: Nội dung CV (text)
            job_title: Tên vị trí tuyển dụng
            job_requirements: Yêu cầu công việc chi tiết
            company_name: Tên công ty (tùy chọn)
            
        Returns:
            Dictionary chứa kết quả đánh giá
        """
        # Chuẩn hóa input
        cv_normalized = self._normalize_cv_content(cv_content)
        job_title = job_title.strip()
        job_requirements = job_requirements.strip()
        
        # Kiểm tra cache
        cache_key = self._get_cache_key(cv_normalized, job_title, job_requirements)
        if cache_key in self._evaluation_cache:
            logger.info(f"Returning cached evaluation for CV")
            return self._evaluation_cache[cache_key]
        
        prompt = f"""Bạn là hệ thống đánh giá CV tự động với tiêu chí KHÁCH QUAN và NHẤT QUÁN.
Nhiệm vụ: Phân tích CV và chấm điểm DỰA TRÊN BẰNG CHỨNG CỤ THỂ có trong CV.

=== QUY TẮC CHẤM ĐIỂM NGHIÊM NGẶT ===

1. KỸ NĂNG KỸ THUẬT (0-30 điểm):
   - Mỗi kỹ năng CHÍNH XÁC khớp với yêu cầu: +5 điểm (tối đa 20 điểm)
   - Kỹ năng liên quan/tương tự: +2 điểm (tối đa 10 điểm)
   - KHÔNG có bằng chứng = 0 điểm

2. KINH NGHIỆM LÀM VIỆC (0-25 điểm):
   - Kinh nghiệm đúng lĩnh vực >= yêu cầu: 25 điểm
   - Kinh nghiệm đúng lĩnh vực < yêu cầu: (số năm thực tế / số năm yêu cầu) × 25
   - Kinh nghiệm lĩnh vực liên quan: 50% số điểm
   - Không có kinh nghiệm liên quan: 0-5 điểm (dựa trên dự án cá nhân)

3. HỌC VẤN/CHỨNG CHỈ (0-20 điểm):
   - Bằng cấp đúng chuyên ngành yêu cầu: 15 điểm
   - Bằng cấp liên quan: 10 điểm
   - Chứng chỉ chuyên môn phù hợp: +2-5 điểm mỗi chứng chỉ

4. KỸ NĂNG MỀM (0-15 điểm):
   - Chỉ tính điểm nếu có BẰNG CHỨNG CỤ THỂ (dự án, thành tích, vai trò)
   - Kỹ năng leadership có bằng chứng: +5 điểm
   - Kỹ năng teamwork có bằng chứng: +5 điểm  
   - Kỹ năng communication có bằng chứng: +5 điểm

5. ĐỘ PHÙ HỢP TỔNG THỂ (0-10 điểm):
   - Phù hợp hoàn toàn với mô tả công việc: 8-10 điểm
   - Phù hợp phần lớn: 5-7 điểm
   - Phù hợp một phần: 2-4 điểm
   - Ít phù hợp: 0-1 điểm

=== THÔNG TIN ĐÁNH GIÁ ===

VỊ TRÍ TUYỂN DỤNG: {job_title}
{f'CÔNG TY: {company_name}' if company_name else ''}

YÊU CẦU CÔNG VIỆC:
{job_requirements}

NỘI DUNG CV ỨNG VIÊN:
{cv_normalized}

=== YÊU CẦU OUTPUT ===

Phân tích TỪNG tiêu chí, liệt kê BẰNG CHỨNG CỤ THỂ từ CV, sau đó cho điểm.
Tổng điểm overall_score = technical_skills + experience + education + soft_skills + overall_fit
Ứng viên ĐẠT YÊU CẦU nếu overall_score >= 85.

Trả về KẾT QUẢ DUY NHẤT dưới dạng JSON (không có text khác):
{{
    "overall_score": <tổng điểm 0-100>,
    "is_qualified": <true nếu >= 85, false nếu < 85>,
    "technical_skills": <0-30>,
    "experience": <0-25>,
    "education": <0-20>,
    "soft_skills": <0-15>,
    "overall_fit": <0-10>,
    "strengths": ["điểm mạnh 1 với bằng chứng cụ thể", "điểm mạnh 2"],
    "weaknesses": ["điểm yếu 1", "điểm yếu 2"],
    "missing_requirements": ["yêu cầu thiếu 1", "yêu cầu thiếu 2"],
    "matched_skills": ["kỹ năng khớp 1", "kỹ năng khớp 2"],
    "recommendation": "TUYỂN DỤNG / XEM XÉT THÊM / KHÔNG PHÙ HỢP - lý do ngắn gọn",
    "summary": "Tóm tắt 2-3 câu về ứng viên dựa trên bằng chứng"
}}"""

        try:
            response = self.model.generate_content(prompt)
            result = self._extract_json(response.text)
            
            if result:
                # Validate và tính lại overall_score để đảm bảo chính xác
                tech = min(30, max(0, result.get('technical_skills', 0)))
                exp = min(25, max(0, result.get('experience', 0)))
                edu = min(20, max(0, result.get('education', 0)))
                soft = min(15, max(0, result.get('soft_skills', 0)))
                fit = min(10, max(0, result.get('overall_fit', 0)))
                
                calculated_score = tech + exp + edu + soft + fit
                result['technical_skills'] = tech
                result['experience'] = exp
                result['education'] = edu
                result['soft_skills'] = soft
                result['overall_fit'] = fit
                result['overall_score'] = calculated_score
                result['is_qualified'] = calculated_score >= 85
                
                # Lưu vào cache
                self._evaluation_cache[cache_key] = result
                
                logger.info(f"CV evaluated with Gemini: Score={calculated_score}, Qualified={result['is_qualified']}")
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
    
    def clear_cache(self):
        """Xóa cache đánh giá"""
        self._evaluation_cache.clear()
        logger.info("Evaluation cache cleared")
    
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
