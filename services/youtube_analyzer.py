"""
YouTube Channel Analyzer Service
Comprehensive analysis using multiple methods:
1. YouTube Data API v3 (official, requires API key)
2. YouTube oEmbed API (free, limited data)  
3. Noembed API (free proxy)
4. Web scraping with ytInitialData extraction
5. Third-party APIs (SocialBlade style)
6. AI-powered analysis using Google Gemini for better accuracy
"""

import re
import json
import logging
import requests
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
from urllib.parse import quote, urlparse, parse_qs
import os

import google.generativeai as genai
from config.settings import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)


class YouTubeAnalyzer:
    """Comprehensive YouTube channel analyzer using multiple data sources"""
    
    # CPM rates by region/niche (USD per 1000 monetized views)
    # REALISTIC 2024-2025 data based on actual creator reports
    # Note: These are CPM (cost per 1000 monetized views), not RPM
    CPM_RATES = {
        # By Niche (primarily for US/Tier 1 audience)
        'finance': {'low': 12.0, 'avg': 20.0, 'high': 40.0},     # Finance, investing, crypto
        'business': {'low': 8.0, 'avg': 15.0, 'high': 30.0},     # Business, entrepreneurship
        'tech': {'low': 5.0, 'avg': 10.0, 'high': 20.0},         # Technology, software
        'education': {'low': 4.0, 'avg': 8.0, 'high': 15.0},     # Educational content
        'health': {'low': 4.0, 'avg': 9.0, 'high': 18.0},        # Health, fitness
        'gaming': {'low': 2.0, 'avg': 4.0, 'high': 8.0},         # Gaming
        'entertainment': {'low': 1.5, 'avg': 3.5, 'high': 7.0},  # Entertainment, vlogs
        'music': {'low': 1.0, 'avg': 2.5, 'high': 5.0},          # Music
        'lifestyle': {'low': 2.0, 'avg': 4.5, 'high': 9.0},      # Lifestyle, beauty
        'food': {'low': 2.0, 'avg': 4.0, 'high': 8.0},           # Food, cooking
        'travel': {'low': 3.0, 'avg': 6.0, 'high': 12.0},        # Travel
        'news': {'low': 3.0, 'avg': 6.0, 'high': 12.0},          # News, politics
        'kids': {'low': 0.5, 'avg': 1.5, 'high': 3.0},           # Kids content (limited ads)
        'default': {'low': 2.0, 'avg': 5.0, 'high': 10.0},       # Default/unknown
        
        # By Country/Region - REALISTIC RPM (what creators actually receive per 1000 views)
        # RPM already factors in: monetized views %, YouTube's 45% cut
        'us': {'low': 2.0, 'avg': 4.5, 'high': 10.0},            # USA - actual RPM
        'uk': {'low': 1.8, 'avg': 4.0, 'high': 8.0},             # UK
        'canada': {'low': 1.5, 'avg': 3.5, 'high': 7.0},         # Canada
        'australia': {'low': 1.5, 'avg': 3.5, 'high': 7.0},      # Australia
        'germany': {'low': 1.2, 'avg': 3.0, 'high': 6.0},        # Germany
        'japan': {'low': 1.0, 'avg': 2.5, 'high': 5.0},          # Japan
        'india': {'low': 0.05, 'avg': 0.15, 'high': 0.40},       # India - very low
        'brazil': {'low': 0.08, 'avg': 0.20, 'high': 0.50},      # Brazil
        'indonesia': {'low': 0.05, 'avg': 0.12, 'high': 0.30},   # Indonesia
        'vietnam': {'low': 0.03, 'avg': 0.10, 'high': 0.30},     # Vietnam - REALISTIC
        'philippines': {'low': 0.05, 'avg': 0.12, 'high': 0.30}, # Philippines
        'thailand': {'low': 0.06, 'avg': 0.15, 'high': 0.35},    # Thailand
        'international': {'low': 0.50, 'avg': 1.50, 'high': 4.0},# Mixed international
    }
    
    # Typical RPM ranges by region (USD per 1000 total views - what creator gets)
    # This is the most accurate metric for earnings calculation
    ACTUAL_RPM = {
        'vietnam': {'low': 0.02, 'avg': 0.08, 'high': 0.25},      # $0.02-$0.25 per 1000 views
        'india': {'low': 0.03, 'avg': 0.10, 'high': 0.30},
        'indonesia': {'low': 0.03, 'avg': 0.08, 'high': 0.25},
        'philippines': {'low': 0.03, 'avg': 0.10, 'high': 0.25},
        'thailand': {'low': 0.04, 'avg': 0.12, 'high': 0.30},
        'brazil': {'low': 0.05, 'avg': 0.15, 'high': 0.40},
        'japan': {'low': 0.50, 'avg': 1.50, 'high': 3.50},
        'germany': {'low': 0.60, 'avg': 1.80, 'high': 4.00},
        'uk': {'low': 1.00, 'avg': 2.50, 'high': 6.00},
        'us': {'low': 1.20, 'avg': 3.00, 'high': 8.00},
        'canada': {'low': 0.80, 'avg': 2.20, 'high': 5.50},
        'australia': {'low': 0.80, 'avg': 2.20, 'high': 5.50},
        'international': {'low': 0.30, 'avg': 1.00, 'high': 3.00},
    }
    
    # Niche keywords for detection
    NICHE_KEYWORDS = {
        'finance': ['finance', 'invest', 'crypto', 'bitcoin', 'stock', 'trading', 'money', 'tài chính', 'đầu tư', 'chứng khoán', 'tiền'],
        'business': ['business', 'entrepreneur', 'startup', 'marketing', 'kinh doanh', 'khởi nghiệp'],
        'tech': ['tech', 'technology', 'software', 'programming', 'code', 'developer', 'công nghệ', 'lập trình', 'review'],
        'education': ['education', 'learn', 'tutorial', 'course', 'học', 'giáo dục', 'hướng dẫn', 'dạy'],
        'health': ['health', 'fitness', 'workout', 'gym', 'diet', 'nutrition', 'sức khỏe', 'tập gym', 'thể dục'],
        'gaming': ['gaming', 'game', 'gameplay', 'gamer', 'playthrough', 'stream', 'chơi game'],
        'entertainment': ['entertainment', 'funny', 'comedy', 'vlog', 'reaction', 'giải trí', 'hài', 'vui'],
        'music': ['music', 'song', 'cover', 'mv', 'official', 'nhạc', 'bài hát', 'ca sĩ'],
        'lifestyle': ['lifestyle', 'beauty', 'fashion', 'makeup', 'skincare', 'làm đẹp', 'thời trang', 'cuộc sống'],
        'food': ['food', 'cooking', 'recipe', 'chef', 'mukbang', 'ẩm thực', 'nấu ăn', 'món ăn'],
        'travel': ['travel', 'trip', 'tour', 'destination', 'du lịch', 'phượt', 'khám phá'],
        'news': ['news', 'politics', 'current', 'tin tức', 'thời sự', 'chính trị'],
        'kids': ['kids', 'children', 'nursery', 'cartoon', 'animation', 'trẻ em', 'thiếu nhi', 'hoạt hình'],
    }
    
    # APIs
    YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
    EXCHANGE_RATE_API = "https://api.exchangerate-api.com/v4/latest/USD"
    NOEMBED_API = "https://noembed.com/embed"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get('YOUTUBE_API_KEY')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        })
        self._exchange_rate_cache = None
        self._exchange_rate_time = None
        
        # Initialize Google Gemini for AI-powered analysis
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            self.ai_model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                generation_config={
                    "temperature": 0.3,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 2048,
                }
            )
            self.ai_enabled = True
            logger.info("Gemini AI initialized for YouTube analysis")
        except Exception as e:
            logger.warning(f"Gemini AI initialization failed: {e}")
            self.ai_model = None
            self.ai_enabled = False
    
    # ==================== AI-Powered Analysis ====================
    
    def analyze_with_ai(self, channel_data: Dict, videos: List[Dict], monthly_data: Dict) -> Dict:
        """Use Gemini AI to analyze channel and provide more accurate earnings estimate"""
        if not self.ai_enabled or not self.ai_model:
            return None
        
        try:
            # Prepare data summary for AI
            channel_summary = {
                'name': channel_data.get('title', 'Unknown'),
                'subscribers': channel_data.get('subscriber_count', 0),
                'total_views': channel_data.get('view_count', 0),
                'video_count': channel_data.get('video_count', 0),
                'country': channel_data.get('country', 'Unknown'),
                'description': channel_data.get('description', '')[:300],
                'channel_age_months': monthly_data.get('channel_age_months', 0),
            }
            
            # Video performance summary
            video_summary = []
            for v in videos[:10]:
                video_summary.append({
                    'title': v.get('title', '')[:50],
                    'views': v.get('view_count', 0),
                    'published': v.get('published_text', '') or v.get('published_at', '')[:10] if v.get('published_at') else ''
                })
            
            prompt = f"""Bạn là chuyên gia phân tích YouTube với kinh nghiệm về monetization và CPM rates.

Phân tích kênh YouTube sau và ước tính thu nhập hàng tháng:

**Thông tin kênh:**
- Tên: {channel_summary['name']}
- Subscribers: {channel_summary['subscribers']:,}
- Tổng views: {channel_summary['total_views']:,}
- Số video: {channel_summary['video_count']}
- Quốc gia: {channel_summary['country']}
- Tuổi kênh: {channel_summary['channel_age_months']} tháng
- Mô tả: {channel_summary['description']}

**Video gần đây (10 video mới nhất):**
{json.dumps(video_summary, ensure_ascii=False, indent=2)}

**Dữ liệu tính toán:**
- Views 30 ngày qua: {monthly_data.get('views_last_30_days', 0):,}
- Video 30 ngày qua: {monthly_data.get('videos_last_30_days', 0)}
- Views TB/video: {monthly_data.get('avg_views_per_video', 0):,}
- Views TB hàng tháng (lifetime): {monthly_data.get('avg_monthly_views_lifetime', 0):,}

Hãy phân tích và trả về JSON với format sau:
{{
    "niche": "tên niche/category của kênh",
    "niche_vi": "tên niche bằng tiếng Việt", 
    "estimated_monthly_views": số views ước tính hàng tháng (số nguyên),
    "cpm_low": CPM thấp (USD, số thập phân),
    "cpm_avg": CPM trung bình (USD, số thập phân),
    "cpm_high": CPM cao (USD, số thập phân),
    "earnings_low": thu nhập thấp USD/tháng (số thập phân),
    "earnings_avg": thu nhập TB USD/tháng (số thập phân),
    "earnings_high": thu nhập cao USD/tháng (số thập phân),
    "monetization_rate": tỷ lệ video được monetize (0.0-1.0),
    "growth_trend": "increasing/stable/decreasing",
    "confidence_score": độ tin cậy 0-100,
    "analysis": "phân tích ngắn gọn bằng tiếng Việt (2-3 câu)"
}}

Lưu ý:
- CPM phụ thuộc vào niche và quốc gia người xem
- Kênh Việt Nam thường có CPM thấp hơn ($0.3-$2.5)
- Chỉ ~40-55% views được monetize
- Xem xét tần suất đăng video và engagement
- Trả về CHỈ JSON, không có text khác"""

            # Call Gemini API
            response = self.ai_model.generate_content(prompt)
            ai_response = response.text.strip()
            
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', ai_response)
            if json_match:
                ai_result = json.loads(json_match.group())
                logger.info(f"Gemini AI analysis successful: {ai_result.get('niche', 'unknown')}")
                return ai_result
            
        except json.JSONDecodeError as e:
            logger.warning(f"Gemini AI response JSON parse error: {e}")
        except Exception as e:
            logger.error(f"Gemini AI analysis error: {e}")
        
        return None
    
    def get_ai_enhanced_earnings(self, ai_analysis: Dict, base_earnings: Dict, exchange_rate: float) -> Dict:
        """Combine AI analysis with base earnings for enhanced accuracy"""
        if not ai_analysis:
            return None
        
        try:
            ai_earnings = {
                'estimated_monthly_views': ai_analysis.get('estimated_monthly_views', 0),
                'niche': ai_analysis.get('niche', 'unknown'),
                'niche_vi': ai_analysis.get('niche_vi', 'Không xác định'),
                'cpm_range': {
                    'low': ai_analysis.get('cpm_low', 1.0),
                    'avg': ai_analysis.get('cpm_avg', 3.0),
                    'high': ai_analysis.get('cpm_high', 6.0)
                },
                'monetization_rate': ai_analysis.get('monetization_rate', 0.5),
                'earnings_usd': {
                    'low': round(ai_analysis.get('earnings_low', 0), 2),
                    'average': round(ai_analysis.get('earnings_avg', 0), 2),
                    'high': round(ai_analysis.get('earnings_high', 0), 2)
                },
                'earnings_vnd': {
                    'low': round(ai_analysis.get('earnings_low', 0) * exchange_rate),
                    'average': round(ai_analysis.get('earnings_avg', 0) * exchange_rate),
                    'high': round(ai_analysis.get('earnings_high', 0) * exchange_rate)
                },
                'growth_trend': ai_analysis.get('growth_trend', 'stable'),
                'confidence_score': ai_analysis.get('confidence_score', 50),
                'ai_analysis': ai_analysis.get('analysis', ''),
                'source': 'ai_enhanced'
            }
            
            return ai_earnings
            
        except Exception as e:
            logger.error(f"Error processing AI earnings: {e}")
            return None
    
    # ==================== Monetization Check ====================
    
    def check_monetization_status(self, channel_data: Dict, videos: List[Dict] = None) -> Dict:
        """
        Check if channel is likely monetized based on various indicators.
        
        YouTube Partner Program Requirements (2024):
        - 1,000+ subscribers
        - 4,000+ public watch hours in past 12 months OR 10M+ Shorts views in 90 days
        - Linked AdSense account
        - No active Community Guidelines strikes
        - Enable 2-Step Verification
        - Access to advanced features
        
        Since we can't directly check monetization, we analyze indicators.
        """
        result = {
            'is_eligible': False,
            'is_likely_monetized': False,
            'eligibility_status': 'unknown',
            'requirements': {
                'subscribers': {
                    'required': 1000,
                    'current': 0,
                    'met': False
                },
                'watch_hours': {
                    'required': 4000,
                    'estimated': 0,
                    'met': False,
                    'note': 'Ước tính từ views (không chính xác 100%)'
                }
            },
            'indicators': [],
            'confidence': 0,
            'reason': ''
        }
        
        subscribers = channel_data.get('subscriber_count', 0)
        total_views = channel_data.get('view_count', 0)
        video_count = channel_data.get('video_count', 0)
        channel_age_months = 0
        
        # Calculate channel age
        created_at = channel_data.get('created_at', '')
        if created_at:
            try:
                if 'T' in created_at:
                    created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    channel_age_days = (datetime.now() - created_date.replace(tzinfo=None)).days
                    channel_age_months = channel_age_days // 30
            except:
                pass
        
        # Check subscriber requirement
        result['requirements']['subscribers']['current'] = subscribers
        result['requirements']['subscribers']['met'] = subscribers >= 1000
        
        # Estimate watch hours from views
        # Average video length assumption: 8 minutes = 0.133 hours
        # Average watch time: ~50% of video length = 4 minutes = 0.067 hours per view
        # Only count views from last 12 months (estimate based on channel activity)
        
        if video_count > 0 and total_views > 0:
            avg_views_per_video = total_views / video_count
            
            # Estimate monthly views
            if channel_age_months > 0:
                monthly_views = total_views / channel_age_months
                yearly_views = monthly_views * 12 if channel_age_months >= 12 else total_views
            else:
                yearly_views = total_views
            
            # Estimate watch hours (assuming 4 minutes average watch time per view)
            estimated_watch_hours = (yearly_views * 4) / 60  # 4 minutes per view
            result['requirements']['watch_hours']['estimated'] = int(estimated_watch_hours)
            result['requirements']['watch_hours']['met'] = estimated_watch_hours >= 4000
        
        # Determine eligibility
        subs_met = result['requirements']['subscribers']['met']
        hours_met = result['requirements']['watch_hours']['met']
        
        if subs_met and hours_met:
            result['is_eligible'] = True
            result['eligibility_status'] = 'eligible'
            result['indicators'].append('✅ Đủ điều kiện tham gia YouTube Partner Program')
        elif subs_met:
            result['eligibility_status'] = 'partial'
            result['indicators'].append('⚠️ Đủ subscribers nhưng có thể chưa đủ giờ xem')
        elif hours_met:
            result['eligibility_status'] = 'partial'
            result['indicators'].append('⚠️ Có thể đủ giờ xem nhưng chưa đủ subscribers')
        else:
            result['eligibility_status'] = 'not_eligible'
            result['indicators'].append('❌ Chưa đủ điều kiện tham gia YouTube Partner Program')
        
        # Additional indicators for monetization
        confidence_score = 0
        
        # 1. Check subscriber count (strong indicator)
        if subscribers >= 100000:
            result['indicators'].append('🌟 Kênh lớn (100K+ subs) - rất có thể đã monetize')
            confidence_score += 40
        elif subscribers >= 10000:
            result['indicators'].append('📈 Kênh trung bình (10K+ subs) - có thể đã monetize')
            confidence_score += 30
        elif subscribers >= 1000:
            result['indicators'].append('📊 Đủ 1000 subscribers - đủ điều kiện đăng ký')
            confidence_score += 20
        
        # 2. Check channel age
        if channel_age_months >= 12:
            result['indicators'].append(f'📅 Kênh hoạt động {channel_age_months} tháng - đủ thời gian để monetize')
            confidence_score += 15
        elif channel_age_months >= 6:
            confidence_score += 10
        
        # 3. Check video count and consistency
        if video_count >= 50:
            result['indicators'].append('🎬 Nhiều video (50+) - kênh chuyên nghiệp')
            confidence_score += 15
        elif video_count >= 20:
            confidence_score += 10
        
        # 4. Check views per video ratio (engagement indicator)
        if video_count > 0:
            avg_views = total_views / video_count
            if avg_views >= 10000:
                result['indicators'].append('🔥 Views/video cao - nội dung chất lượng')
                confidence_score += 15
            elif avg_views >= 1000:
                confidence_score += 10
        
        # 5. Analyze recent videos for monetization signs
        if videos:
            recent_high_views = sum(1 for v in videos[:10] if v.get('view_count', 0) >= 1000)
            if recent_high_views >= 5:
                result['indicators'].append('📹 Video gần đây có nhiều views - kênh đang active')
                confidence_score += 10
        
        # Determine if likely monetized
        result['confidence'] = min(confidence_score, 100)
        
        if result['is_eligible'] and confidence_score >= 50:
            result['is_likely_monetized'] = True
            result['reason'] = 'Kênh đủ điều kiện và có nhiều dấu hiệu đã bật kiếm tiền'
        elif result['is_eligible'] and confidence_score >= 30:
            result['is_likely_monetized'] = True
            result['reason'] = 'Kênh có thể đã bật kiếm tiền (đủ điều kiện cơ bản)'
        elif result['is_eligible']:
            result['is_likely_monetized'] = False
            result['reason'] = 'Kênh đủ điều kiện nhưng chưa chắc đã đăng ký monetize'
        else:
            result['is_likely_monetized'] = False
            if not subs_met:
                result['reason'] = f'Cần thêm {1000 - subscribers:,} subscribers để đủ điều kiện'
            else:
                result['reason'] = 'Cần thêm giờ xem để đủ điều kiện'
        
        return result
    
    # ==================== URL Parsing ====================
    
    def parse_youtube_url(self, url: str) -> Dict:
        """Parse YouTube URL to extract channel identifier"""
        url = url.strip()
        result = {'type': None, 'value': None, 'original': url}
        
        # Direct @handle
        if url.startswith('@'):
            result['type'] = 'handle'
            result['value'] = url
            return result
        
        # Add protocol if missing
        if not url.startswith('http'):
            url = 'https://' + url
        
        # Parse URL
        try:
            parsed = urlparse(url)
            path = parsed.path.strip('/')
            
            # youtube.com/channel/UC...
            if '/channel/' in url:
                match = re.search(r'/channel/(UC[a-zA-Z0-9_-]{22})', url)
                if match:
                    result['type'] = 'channel_id'
                    result['value'] = match.group(1)
                    return result
            
            # youtube.com/@handle
            if '/@' in url:
                match = re.search(r'/@([a-zA-Z0-9_.-]+)', url)
                if match:
                    result['type'] = 'handle'
                    result['value'] = '@' + match.group(1)
                    return result
            
            # youtube.com/c/customname
            if '/c/' in url:
                match = re.search(r'/c/([a-zA-Z0-9_.-]+)', url)
                if match:
                    result['type'] = 'custom_url'
                    result['value'] = match.group(1)
                    return result
            
            # youtube.com/user/username
            if '/user/' in url:
                match = re.search(r'/user/([a-zA-Z0-9_.-]+)', url)
                if match:
                    result['type'] = 'legacy_username'
                    result['value'] = match.group(1)
                    return result
            
            # Direct channel ID
            if re.match(r'^UC[a-zA-Z0-9_-]{22}$', url):
                result['type'] = 'channel_id'
                result['value'] = url
                return result
                
        except Exception as e:
            logger.error(f"URL parse error: {e}")
        
        return result
    
    # ==================== YouTube Data API v3 ====================
    
    def get_channel_by_id_api(self, channel_id: str) -> Optional[Dict]:
        """Get channel info using YouTube Data API v3 by channel ID"""
        if not self.api_key:
            logger.info("No YouTube API key available")
            return None
        
        try:
            params = {
                'part': 'snippet,statistics,brandingSettings,contentDetails',
                'id': channel_id,
                'key': self.api_key
            }
            
            response = self.session.get(
                f"{self.YOUTUBE_API_BASE}/channels",
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('items'):
                    return self._parse_api_response(data['items'][0])
            else:
                logger.warning(f"YouTube API error: {response.status_code} - {response.text[:200]}")
                
        except Exception as e:
            logger.error(f"YouTube API error: {e}")
        
        return None
    
    def get_channel_by_handle_api(self, handle: str) -> Optional[Dict]:
        """Get channel info using YouTube Data API v3 by handle"""
        if not self.api_key:
            return None
        
        try:
            # Remove @ if present
            handle = handle.lstrip('@')
            
            params = {
                'part': 'snippet,statistics,brandingSettings,contentDetails',
                'forHandle': handle,
                'key': self.api_key
            }
            
            response = self.session.get(
                f"{self.YOUTUBE_API_BASE}/channels",
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('items'):
                    return self._parse_api_response(data['items'][0])
            
            # Try search as fallback
            return self._search_channel_api(handle)
            
        except Exception as e:
            logger.error(f"YouTube API handle lookup error: {e}")
        
        return None
    
    def get_channel_by_username_api(self, username: str) -> Optional[Dict]:
        """Get channel info using YouTube Data API v3 by legacy username"""
        if not self.api_key:
            return None
        
        try:
            params = {
                'part': 'snippet,statistics,brandingSettings,contentDetails',
                'forUsername': username,
                'key': self.api_key
            }
            
            response = self.session.get(
                f"{self.YOUTUBE_API_BASE}/channels",
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('items'):
                    return self._parse_api_response(data['items'][0])
                    
        except Exception as e:
            logger.error(f"YouTube API username lookup error: {e}")
        
        return None
    
    def _search_channel_api(self, query: str) -> Optional[Dict]:
        """Search for channel using YouTube Data API"""
        if not self.api_key:
            return None
        
        try:
            params = {
                'part': 'snippet',
                'q': query,
                'type': 'channel',
                'maxResults': 1,
                'key': self.api_key
            }
            
            response = self.session.get(
                f"{self.YOUTUBE_API_BASE}/search",
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('items'):
                    channel_id = data['items'][0]['snippet']['channelId']
                    return self.get_channel_by_id_api(channel_id)
                    
        except Exception as e:
            logger.error(f"YouTube search API error: {e}")
        
        return None
    
    def _parse_api_response(self, item: Dict) -> Dict:
        """Parse YouTube Data API response into standard format"""
        snippet = item.get('snippet', {})
        stats = item.get('statistics', {})
        branding = item.get('brandingSettings', {}).get('channel', {})
        content_details = item.get('contentDetails', {})
        
        return {
            'channel_id': item.get('id', ''),
            'title': snippet.get('title', 'Unknown'),
            'description': snippet.get('description', '')[:500],
            'custom_url': snippet.get('customUrl', ''),
            'thumbnail': snippet.get('thumbnails', {}).get('high', {}).get('url', '') or 
                        snippet.get('thumbnails', {}).get('medium', {}).get('url', '') or
                        snippet.get('thumbnails', {}).get('default', {}).get('url', ''),
            'banner': branding.get('bannerExternalUrl', ''),
            'subscriber_count': int(stats.get('subscriberCount', 0)),
            'view_count': int(stats.get('viewCount', 0)),
            'video_count': int(stats.get('videoCount', 0)),
            'hidden_subscriber_count': stats.get('hiddenSubscriberCount', False),
            'created_at': snippet.get('publishedAt', ''),
            'country': snippet.get('country', branding.get('country', 'Unknown')),
            'keywords': branding.get('keywords', ''),
            'uploads_playlist': content_details.get('relatedPlaylists', {}).get('uploads', ''),
            'source': 'youtube_api'
        }
    
    # ==================== Get Recent Videos ====================
    
    def get_recent_videos(self, channel_id: str, max_results: int = 30) -> List[Dict]:
        """Get recent videos from channel to calculate actual monthly views"""
        videos = []
        
        # Method 1: YouTube Data API
        if self.api_key:
            videos = self._get_videos_via_api(channel_id, max_results)
        
        # Method 2: Scrape videos page if API not available or failed
        if not videos:
            videos = self._scrape_recent_videos(channel_id, max_results)
        
        return videos
    
    def _get_videos_via_api(self, channel_id: str, max_results: int = 30) -> List[Dict]:
        """Get videos using YouTube Data API"""
        if not self.api_key:
            return []
        
        try:
            # First, get uploads playlist ID
            params = {
                'part': 'contentDetails',
                'id': channel_id,
                'key': self.api_key
            }
            
            response = self.session.get(
                f"{self.YOUTUBE_API_BASE}/channels",
                params=params,
                timeout=15
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            items = data.get('items', [])
            if not items:
                return []
            
            uploads_playlist = items[0].get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads', '')
            if not uploads_playlist:
                return []
            
            # Get videos from uploads playlist
            params = {
                'part': 'snippet,contentDetails',
                'playlistId': uploads_playlist,
                'maxResults': min(max_results, 50),
                'key': self.api_key
            }
            
            response = self.session.get(
                f"{self.YOUTUBE_API_BASE}/playlistItems",
                params=params,
                timeout=15
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            video_ids = []
            
            for item in data.get('items', []):
                video_id = item.get('contentDetails', {}).get('videoId', '')
                if video_id:
                    video_ids.append(video_id)
            
            if not video_ids:
                return []
            
            # Get video statistics
            params = {
                'part': 'snippet,statistics,contentDetails',
                'id': ','.join(video_ids[:50]),
                'key': self.api_key
            }
            
            response = self.session.get(
                f"{self.YOUTUBE_API_BASE}/videos",
                params=params,
                timeout=15
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            videos = []
            
            for item in data.get('items', []):
                snippet = item.get('snippet', {})
                stats = item.get('statistics', {})
                
                videos.append({
                    'video_id': item.get('id', ''),
                    'title': snippet.get('title', ''),
                    'published_at': snippet.get('publishedAt', ''),
                    'view_count': int(stats.get('viewCount', 0)),
                    'like_count': int(stats.get('likeCount', 0)),
                    'comment_count': int(stats.get('commentCount', 0)),
                })
            
            return videos
            
        except Exception as e:
            logger.error(f"Error getting videos via API: {e}")
            return []
    
    def _scrape_recent_videos(self, channel_id: str, max_results: int = 30) -> List[Dict]:
        """Scrape recent videos from channel videos page"""
        try:
            url = f"https://www.youtube.com/channel/{channel_id}/videos"
            response = self.session.get(url, timeout=20)
            
            if response.status_code != 200:
                return []
            
            html = response.text
            initial_data = self._extract_yt_initial_data(html)
            
            if not initial_data:
                return []
            
            videos = []
            
            # Navigate to videos grid
            tabs = initial_data.get('contents', {}).get('twoColumnBrowseResultsRenderer', {}).get('tabs', [])
            
            for tab in tabs:
                tab_renderer = tab.get('tabRenderer', {})
                if tab_renderer.get('selected'):
                    content = tab_renderer.get('content', {})
                    
                    # Rich grid
                    rich_grid = content.get('richGridRenderer', {})
                    for item in rich_grid.get('contents', [])[:max_results]:
                        video_renderer = item.get('richItemRenderer', {}).get('content', {}).get('videoRenderer', {})
                        if video_renderer:
                            video_data = self._parse_video_renderer(video_renderer)
                            if video_data:
                                videos.append(video_data)
                    
                    # Section list renderer
                    section_list = content.get('sectionListRenderer', {})
                    for section in section_list.get('contents', []):
                        items = section.get('itemSectionRenderer', {}).get('contents', [])
                        for item in items:
                            grid = item.get('gridRenderer', {})
                            for grid_item in grid.get('items', [])[:max_results]:
                                video_renderer = grid_item.get('gridVideoRenderer', {})
                                if video_renderer:
                                    video_data = self._parse_video_renderer(video_renderer)
                                    if video_data:
                                        videos.append(video_data)
            
            return videos[:max_results]
            
        except Exception as e:
            logger.error(f"Error scraping videos: {e}")
            return []
    
    def _parse_video_renderer(self, renderer: Dict) -> Optional[Dict]:
        """Parse video renderer data"""
        try:
            video_id = renderer.get('videoId', '')
            if not video_id:
                return None
            
            title = renderer.get('title', {}).get('runs', [{}])[0].get('text', '') or \
                   renderer.get('title', {}).get('simpleText', '')
            
            # View count
            view_text = renderer.get('viewCountText', {}).get('simpleText', '') or \
                       renderer.get('viewCountText', {}).get('runs', [{}])[0].get('text', '')
            view_count = self._parse_count_text(view_text)
            
            # Published time
            published = renderer.get('publishedTimeText', {}).get('simpleText', '')
            
            return {
                'video_id': video_id,
                'title': title,
                'view_count': view_count,
                'published_text': published,
                'published_at': self._parse_relative_time(published)
            }
        except:
            return None
    
    def _parse_relative_time(self, text: str) -> str:
        """Parse relative time text to approximate ISO date"""
        from datetime import timedelta
        
        if not text:
            return ''
        
        text = text.lower()
        now = datetime.now()
        
        patterns = [
            (r'(\d+)\s*(second|giây)', 'seconds'),
            (r'(\d+)\s*(minute|phút)', 'minutes'),
            (r'(\d+)\s*(hour|giờ)', 'hours'),
            (r'(\d+)\s*(day|ngày)', 'days'),
            (r'(\d+)\s*(week|tuần)', 'weeks'),
            (r'(\d+)\s*(month|tháng)', 'months'),
            (r'(\d+)\s*(year|năm)', 'years'),
        ]
        
        for pattern, unit in patterns:
            match = re.search(pattern, text)
            if match:
                value = int(match.group(1))
                if unit == 'months':
                    delta = timedelta(days=value * 30)
                elif unit == 'years':
                    delta = timedelta(days=value * 365)
                elif unit == 'weeks':
                    delta = timedelta(weeks=value)
                else:
                    delta = timedelta(**{unit: value})
                
                return (now - delta).isoformat()
        
        return ''
    
    def calculate_monthly_views(self, videos: List[Dict], total_views: int, video_count: int, channel_created: str = '') -> Dict:
        """Calculate estimated monthly views based on recent video performance"""
        now = datetime.now()
        current_month = now.month
        current_year = now.year
        
        result = {
            'calculation_method': '',
            'videos_analyzed': 0,
            'videos_last_30_days': 0,
            'views_last_30_days': 0,
            'avg_views_per_video': 0,
            'estimated_monthly_views': 0,
            'views_this_month': 0,
            'days_in_month': 30,
            'channel_age_months': 0,
            'avg_monthly_views_lifetime': 0,
        }
        
        # Calculate channel age
        if channel_created:
            try:
                if 'T' in channel_created:
                    created_date = datetime.fromisoformat(channel_created.replace('Z', '+00:00'))
                else:
                    # Try parsing different formats
                    for fmt in ['%Y-%m-%d', '%b %d, %Y', '%d %b %Y']:
                        try:
                            created_date = datetime.strptime(channel_created, fmt)
                            break
                        except:
                            continue
                
                channel_age_days = (now - created_date.replace(tzinfo=None)).days
                result['channel_age_months'] = max(1, channel_age_days // 30)
            except:
                pass
        
        # Calculate lifetime average
        if result['channel_age_months'] > 0 and total_views > 0:
            result['avg_monthly_views_lifetime'] = int(total_views / result['channel_age_months'])
        
        # If we have recent videos with data
        if videos:
            result['videos_analyzed'] = len(videos)
            
            # Filter videos from last 30 days
            thirty_days_ago = now - timedelta(days=30)
            recent_videos = []
            
            for video in videos:
                pub_date = video.get('published_at', '')
                if pub_date:
                    try:
                        video_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00')).replace(tzinfo=None)
                        if video_date >= thirty_days_ago:
                            recent_videos.append(video)
                    except:
                        pass
            
            result['videos_last_30_days'] = len(recent_videos)
            
            if recent_videos:
                # Calculate views from videos in last 30 days
                total_recent_views = sum(v.get('view_count', 0) for v in recent_videos)
                result['views_last_30_days'] = total_recent_views
                result['avg_views_per_video'] = int(total_recent_views / len(recent_videos))
                result['estimated_monthly_views'] = total_recent_views
                result['calculation_method'] = 'recent_30_days'
            else:
                # Use all analyzed videos
                total_analyzed_views = sum(v.get('view_count', 0) for v in videos)
                result['avg_views_per_video'] = int(total_analyzed_views / len(videos))
                
                # Estimate upload frequency
                if len(videos) >= 2:
                    # Get date range of videos
                    dates = []
                    for v in videos:
                        pub = v.get('published_at', '')
                        if pub:
                            try:
                                dates.append(datetime.fromisoformat(pub.replace('Z', '+00:00')).replace(tzinfo=None))
                            except:
                                pass
                    
                    if len(dates) >= 2:
                        date_range = (max(dates) - min(dates)).days
                        if date_range > 0:
                            videos_per_month = (len(videos) / date_range) * 30
                            result['estimated_monthly_views'] = int(result['avg_views_per_video'] * videos_per_month)
                            result['calculation_method'] = 'video_frequency'
                
                if result['estimated_monthly_views'] == 0:
                    # Fallback: assume 4 videos per month
                    result['estimated_monthly_views'] = result['avg_views_per_video'] * 4
                    result['calculation_method'] = 'avg_estimate'
        else:
            # No video data, use total views / channel age
            if result['avg_monthly_views_lifetime'] > 0:
                result['estimated_monthly_views'] = result['avg_monthly_views_lifetime']
                result['calculation_method'] = 'lifetime_average'
            elif video_count > 0 and total_views > 0:
                # Rough estimate
                avg_per_video = total_views / video_count
                result['avg_views_per_video'] = int(avg_per_video)
                result['estimated_monthly_views'] = int(avg_per_video * 4)  # Assume 4 videos/month
                result['calculation_method'] = 'total_average'
        
        return result
    
    # ==================== Web Scraping ====================
    
    def scrape_channel_page(self, url: str) -> Optional[Dict]:
        """Scrape channel data from YouTube page"""
        try:
            # Ensure proper URL format
            if not url.startswith('http'):
                url = f"https://www.youtube.com/{url}"
            
            # Add /about to get more info
            about_url = url.rstrip('/') + '/about'
            
            response = self.session.get(about_url, timeout=20, allow_redirects=True)
            
            if response.status_code != 200:
                # Try without /about
                response = self.session.get(url, timeout=20, allow_redirects=True)
            
            if response.status_code != 200:
                logger.warning(f"Failed to fetch channel page: {response.status_code}")
                return None
            
            html = response.text
            
            # Extract ytInitialData
            initial_data = self._extract_yt_initial_data(html)
            
            if initial_data:
                return self._parse_initial_data(initial_data, html)
            
            # Fallback to regex parsing
            return self._parse_html_fallback(html)
            
        except Exception as e:
            logger.error(f"Scraping error: {e}")
            return None
    
    def _extract_yt_initial_data(self, html: str) -> Optional[Dict]:
        """Extract ytInitialData JSON from page"""
        patterns = [
            r'var\s+ytInitialData\s*=\s*({.+?})\s*;\s*</script>',
            r'window\s*\[\s*["\']ytInitialData["\']\s*\]\s*=\s*({.+?})\s*;',
            r'ytInitialData\s*=\s*({.+?})\s*;',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _parse_initial_data(self, data: Dict, html: str = '') -> Optional[Dict]:
        """Parse ytInitialData for channel info"""
        result = {
            'channel_id': '',
            'title': 'Unknown',
            'description': '',
            'thumbnail': '',
            'subscriber_count': 0,
            'view_count': 0,
            'video_count': 0,
            'created_at': '',
            'country': 'Unknown',
            'source': 'scraping'
        }
        
        try:
            # Get header data
            header = data.get('header', {})
            
            # Try c4TabbedHeaderRenderer (most common)
            c4_header = header.get('c4TabbedHeaderRenderer', {})
            if c4_header:
                result['channel_id'] = c4_header.get('channelId', '')
                result['title'] = c4_header.get('title', 'Unknown')
                
                # Subscribers
                sub_text = c4_header.get('subscriberCountText', {})
                if isinstance(sub_text, dict):
                    sub_str = sub_text.get('simpleText', '') or self._extract_runs_text(sub_text)
                    result['subscriber_count'] = self._parse_count_text(sub_str)
                
                # Videos count
                videos_text = c4_header.get('videosCountText', {})
                if isinstance(videos_text, dict):
                    video_str = videos_text.get('runs', [{}])[0].get('text', '')
                    result['video_count'] = self._parse_count_text(video_str)
                
                # Avatar
                avatar = c4_header.get('avatar', {}).get('thumbnails', [])
                if avatar:
                    result['thumbnail'] = avatar[-1].get('url', '').split('=')[0]
            
            # Try pageHeaderRenderer (newer format)
            page_header = header.get('pageHeaderRenderer', {})
            if page_header:
                content = page_header.get('content', {}).get('pageHeaderViewModel', {})
                
                # Title
                title_obj = content.get('title', {}).get('dynamicTextViewModel', {}).get('text', {})
                result['title'] = title_obj.get('content', result['title'])
                
                # Metadata rows contain subs and videos
                metadata = content.get('metadata', {}).get('contentMetadataViewModel', {})
                for row in metadata.get('metadataRows', []):
                    for part in row.get('metadataParts', []):
                        text = part.get('text', {}).get('content', '')
                        text_lower = text.lower()
                        
                        if any(x in text_lower for x in ['subscriber', 'người đăng ký', 'đăng ký']):
                            result['subscriber_count'] = self._parse_count_text(text)
                        elif 'video' in text_lower:
                            result['video_count'] = self._parse_count_text(text)
                        elif any(x in text_lower for x in ['view', 'lượt xem']):
                            result['view_count'] = self._parse_count_text(text)
                
                # Avatar
                image = content.get('image', {})
                avatar_vm = image.get('decoratedAvatarViewModel', {}).get('avatar', {}).get('avatarViewModel', {})
                sources = avatar_vm.get('image', {}).get('sources', [])
                if sources:
                    result['thumbnail'] = sources[-1].get('url', '').split('=')[0]
            
            # Get metadata from channelMetadataRenderer
            metadata = data.get('metadata', {}).get('channelMetadataRenderer', {})
            if metadata:
                result['channel_id'] = result['channel_id'] or metadata.get('externalId', '')
                result['title'] = result['title'] if result['title'] != 'Unknown' else metadata.get('title', 'Unknown')
                result['description'] = metadata.get('description', '')[:500]
                
                avatar = metadata.get('avatar', {}).get('thumbnails', [])
                if avatar and not result['thumbnail']:
                    result['thumbnail'] = avatar[-1].get('url', '').split('=')[0]
            
            # Try to get view count from about tab
            self._extract_about_stats(data, result)
            
            # Fallback to HTML regex if needed
            if result['subscriber_count'] == 0 or result['view_count'] == 0:
                self._extract_stats_from_html(html, result)
            
        except Exception as e:
            logger.error(f"Error parsing initial data: {e}")
        
        return result
    
    def _extract_about_stats(self, data: Dict, result: Dict):
        """Extract stats from about tab in ytInitialData"""
        try:
            tabs = data.get('contents', {}).get('twoColumnBrowseResultsRenderer', {}).get('tabs', [])
            
            for tab in tabs:
                tab_renderer = tab.get('tabRenderer', {})
                title = tab_renderer.get('title', '').lower()
                
                if title in ['about', 'giới thiệu', 'thông tin']:
                    content = tab_renderer.get('content', {})
                    section_list = content.get('sectionListRenderer', {}).get('contents', [])
                    
                    for section in section_list:
                        items = section.get('itemSectionRenderer', {}).get('contents', [])
                        for item in items:
                            about = item.get('channelAboutFullMetadataRenderer', {})
                            if about:
                                # View count
                                view_text = about.get('viewCountText', {}).get('simpleText', '')
                                if view_text:
                                    result['view_count'] = self._parse_count_text(view_text)
                                
                                # Join date
                                joined = about.get('joinedDateText', {}).get('runs', [])
                                if joined:
                                    result['created_at'] = ''.join(r.get('text', '') for r in joined)
                                
                                # Country
                                country = about.get('country', {}).get('simpleText', '')
                                if country:
                                    result['country'] = country
                                
                                # Links
                                description = about.get('description', {}).get('simpleText', '')
                                if description:
                                    result['description'] = description[:500]
                                
                                return
                                
        except Exception as e:
            logger.debug(f"Error extracting about stats: {e}")
    
    def _extract_stats_from_html(self, html: str, result: Dict):
        """Fallback: Extract stats using regex from HTML"""
        if not html:
            return
        
        # Subscriber patterns
        if result['subscriber_count'] == 0:
            sub_patterns = [
                r'"subscriberCountText":\s*{\s*"simpleText":\s*"([^"]+)"',
                r'"subscriberCountText":\s*{[^}]*"label":\s*"([^"]+)"',
                r'(\d+(?:[.,]\d+)?)\s*(?:subscribers?|người đăng ký)',
                r'(\d+(?:[.,]\d+)?[KMBTr]*)\s*(?:subscribers?|người đăng ký)',
            ]
            for pattern in sub_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    count = self._parse_count_text(match.group(1))
                    if count > 0:
                        result['subscriber_count'] = count
                        break
        
        # View count patterns
        if result['view_count'] == 0:
            view_patterns = [
                r'"viewCount":\s*"(\d+)"',
                r'"viewCountText":\s*{\s*"simpleText":\s*"([^"]+)"',
                r'(\d[\d,.\s]+)\s*(?:views?|lượt xem)',
            ]
            for pattern in view_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    count = self._parse_count_text(match.group(1))
                    if count > 0:
                        result['view_count'] = count
                        break
        
        # Video count patterns
        if result['video_count'] == 0:
            video_patterns = [
                r'"videosCountText":\s*{[^}]*"text":\s*"([^"]+)"',
                r'(\d[\d,.\s]+)\s*videos?',
            ]
            for pattern in video_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    count = self._parse_count_text(match.group(1))
                    if count > 0:
                        result['video_count'] = count
                        break
        
        # Channel name from title
        if result['title'] == 'Unknown':
            title_match = re.search(r'<title>([^<]+?)(?:\s*-\s*YouTube)?</title>', html)
            if title_match:
                result['title'] = title_match.group(1).strip()
        
        # Channel ID
        if not result['channel_id']:
            id_match = re.search(r'"channelId":\s*"(UC[a-zA-Z0-9_-]{22})"', html)
            if id_match:
                result['channel_id'] = id_match.group(1)
    
    def _parse_html_fallback(self, html: str) -> Dict:
        """Complete fallback parsing when ytInitialData fails"""
        result = {
            'channel_id': '',
            'title': 'Unknown',
            'description': '',
            'thumbnail': '',
            'subscriber_count': 0,
            'view_count': 0,
            'video_count': 0,
            'created_at': '',
            'country': 'Unknown',
            'source': 'html_fallback'
        }
        
        self._extract_stats_from_html(html, result)
        
        # Try to get thumbnail
        thumb_match = re.search(r'"avatar":\s*{\s*"thumbnails":\s*\[\s*{\s*"url":\s*"([^"]+)"', html)
        if thumb_match:
            result['thumbnail'] = thumb_match.group(1).replace('\\u0026', '&').split('=')[0]
        
        return result
    
    def _extract_runs_text(self, obj: Dict) -> str:
        """Extract text from 'runs' format"""
        runs = obj.get('runs', [])
        return ''.join(run.get('text', '') for run in runs)
    
    def _parse_count_text(self, text: str) -> int:
        """Parse count from text like '1.5M', '100K', '1,234,567', '1.5Tr', etc."""
        if not text:
            return 0
        
        text = str(text).strip().upper()
        
        # Remove common suffixes/words
        remove_words = [
            'SUBSCRIBERS', 'SUBSCRIBER', 'NGƯỜI ĐĂNG KÝ', 'ĐĂNG KÝ',
            'VIEWS', 'VIEW', 'LƯỢT XEM',
            'VIDEOS', 'VIDEO',
        ]
        for word in remove_words:
            text = text.replace(word, '')
        
        text = text.strip().replace(',', '').replace(' ', '')
        
        # Vietnamese multipliers
        vn_multipliers = {
            'TR': 1000000,      # Triệu
            'TRIỆU': 1000000,
            'N': 1000,          # Nghìn
            'NGHÌN': 1000,
            'TỶ': 1000000000,
        }
        
        # International multipliers
        int_multipliers = {
            'K': 1000,
            'M': 1000000,
            'B': 1000000000,
            'T': 1000000000000,
        }
        
        all_multipliers = {**vn_multipliers, **int_multipliers}
        
        for suffix, multiplier in all_multipliers.items():
            if suffix in text:
                try:
                    num_str = re.sub(r'[^\d.,]', '', text.split(suffix)[0])
                    num_str = num_str.replace(',', '.')
                    if num_str:
                        return int(float(num_str) * multiplier)
                except:
                    pass
        
        # Plain number
        try:
            num_str = re.sub(r'[^\d]', '', text)
            if num_str:
                return int(num_str)
        except:
            pass
        
        return 0
    
    # ==================== Channel ID Resolution ====================
    
    def resolve_to_channel_id(self, identifier: Dict) -> Optional[str]:
        """Resolve any identifier type to channel ID"""
        if identifier['type'] == 'channel_id':
            return identifier['value']
        
        # Try to get channel ID from page
        url = self._build_channel_url(identifier)
        
        try:
            response = self.session.get(url, timeout=15, allow_redirects=True)
            if response.status_code == 200:
                # Look for channel ID in response
                patterns = [
                    r'"channelId":\s*"(UC[a-zA-Z0-9_-]{22})"',
                    r'"externalId":\s*"(UC[a-zA-Z0-9_-]{22})"',
                    r'/channel/(UC[a-zA-Z0-9_-]{22})',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, response.text)
                    if match:
                        return match.group(1)
        except Exception as e:
            logger.error(f"Error resolving channel ID: {e}")
        
        return None
    
    def _build_channel_url(self, identifier: Dict) -> str:
        """Build YouTube channel URL from identifier"""
        id_type = identifier['type']
        value = identifier['value']
        
        if id_type == 'channel_id':
            return f"https://www.youtube.com/channel/{value}"
        elif id_type == 'handle':
            handle = value if value.startswith('@') else f"@{value}"
            return f"https://www.youtube.com/{handle}"
        elif id_type == 'custom_url':
            return f"https://www.youtube.com/c/{value}"
        elif id_type == 'legacy_username':
            return f"https://www.youtube.com/user/{value}"
        else:
            return f"https://www.youtube.com/{value}"
    
    # ==================== Exchange Rate ====================
    
    def get_exchange_rate(self) -> float:
        """Get current USD to VND exchange rate with caching"""
        from datetime import timedelta
        
        # Use cached rate if less than 1 hour old
        if self._exchange_rate_cache and self._exchange_rate_time:
            if datetime.now() - self._exchange_rate_time < timedelta(hours=1):
                return self._exchange_rate_cache
        
        try:
            response = self.session.get(self.EXCHANGE_RATE_API, timeout=10)
            if response.status_code == 200:
                data = response.json()
                rate = data.get('rates', {}).get('VND', 25000)
                self._exchange_rate_cache = rate
                self._exchange_rate_time = datetime.now()
                return rate
        except Exception as e:
            logger.warning(f"Exchange rate API error: {e}")
        
        return self._exchange_rate_cache or 25000
    
    # ==================== Earnings Estimation ====================
    
    def detect_channel_niche(self, channel_data: Dict, videos: List[Dict] = None) -> str:
        """Detect channel niche from title, description, and video titles"""
        text_to_analyze = []
        
        # Add channel info
        text_to_analyze.append(channel_data.get('title', '').lower())
        text_to_analyze.append(channel_data.get('description', '').lower())
        text_to_analyze.append(channel_data.get('keywords', '').lower())
        
        # Add video titles
        if videos:
            for video in videos[:10]:
                text_to_analyze.append(video.get('title', '').lower())
        
        combined_text = ' '.join(text_to_analyze)
        
        # Score each niche
        niche_scores = {}
        for niche, keywords in self.NICHE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in combined_text)
            if score > 0:
                niche_scores[niche] = score
        
        if niche_scores:
            return max(niche_scores, key=niche_scores.get)
        
        return 'default'
    
    def get_audience_region(self, channel_data: Dict) -> str:
        """Estimate primary audience region based on channel info"""
        country = channel_data.get('country', '').lower()
        title = channel_data.get('title', '').lower()
        description = channel_data.get('description', '').lower()
        
        # Map country codes to regions
        country_map = {
            'vn': 'vietnam', 'vietnam': 'vietnam', 'việt nam': 'vietnam',
            'us': 'us', 'united states': 'us', 'usa': 'us',
            'gb': 'uk', 'uk': 'uk', 'united kingdom': 'uk',
            'ca': 'canada', 'canada': 'canada',
            'au': 'australia', 'australia': 'australia',
            'de': 'germany', 'germany': 'germany',
            'jp': 'japan', 'japan': 'japan',
            'in': 'india', 'india': 'india',
            'br': 'brazil', 'brazil': 'brazil',
            'id': 'indonesia', 'indonesia': 'indonesia',
            'ph': 'philippines', 'philippines': 'philippines',
            'th': 'thailand', 'thailand': 'thailand',
        }
        
        # Check country code
        if country in country_map:
            return country_map[country]
        
        # Check for Vietnamese content indicators
        vn_indicators = ['việt', 'tiếng việt', 'người việt', 'viet', 'vietnam']
        if any(ind in title or ind in description for ind in vn_indicators):
            return 'vietnam'
        
        # Default to international
        return 'international'
    
    def calculate_rpm(self, niche: str, region: str, engagement_rate: float = 0.05, avg_video_length_mins: float = 10) -> Dict:
        """
        Calculate RPM (Revenue Per Mille) using ACTUAL RPM data.
        
        RPM = What creator actually receives per 1000 TOTAL views
        (Already includes: monetized views %, YouTube's 45% cut, ad rates)
        
        Key factors:
        1. Audience geography (most important - 90% of variation)
        2. Channel niche (adds 10-30% for premium niches in Tier 1 countries)
        3. Video length (8+ mins = mid-roll ads = +20-40% RPM)
        4. Engagement rate (higher = slightly better fill rate)
        5. Seasonality (Q4 = +10-20%)
        """
        # Use ACTUAL RPM data (what creators really get)
        base_rpm = self.ACTUAL_RPM.get(region, self.ACTUAL_RPM['international'])
        
        # Start with base RPM for the region
        rpm = {
            'low': base_rpm['low'],
            'avg': base_rpm['avg'],
            'high': base_rpm['high']
        }
        
        # Niche multiplier - only significant for Tier 1 countries
        niche_multipliers = {
            'finance': 1.5,
            'business': 1.4,
            'tech': 1.3,
            'education': 1.2,
            'health': 1.25,
            'travel': 1.15,
            'news': 1.1,
            'lifestyle': 1.1,
            'food': 1.05,
            'gaming': 0.9,
            'entertainment': 0.95,
            'music': 0.85,
            'kids': 0.6,  # Limited ads
            'default': 1.0
        }
        
        niche_mult = niche_multipliers.get(niche, 1.0)
        
        # Niche only affects Tier 1 countries significantly
        if region in ['us', 'uk', 'canada', 'australia', 'germany']:
            rpm['avg'] *= niche_mult
            rpm['high'] *= niche_mult
        elif region in ['japan']:
            rpm['avg'] *= (1 + (niche_mult - 1) * 0.5)  # Half effect
            rpm['high'] *= (1 + (niche_mult - 1) * 0.5)
        # For low CPM regions (VN, India, etc.), niche has minimal effect
        else:
            rpm['avg'] *= (1 + (niche_mult - 1) * 0.1)  # 10% of niche effect
            rpm['high'] *= (1 + (niche_mult - 1) * 0.15)
        
        # Video length bonus (8+ mins = mid-roll ads)
        if avg_video_length_mins >= 8:
            length_multiplier = 1.3  # +30% for mid-roll eligible
        elif avg_video_length_mins >= 5:
            length_multiplier = 1.1  # Slightly better
        else:
            length_multiplier = 1.0  # Short videos - only pre-roll
        
        rpm['avg'] *= length_multiplier
        rpm['high'] *= length_multiplier
        
        # Engagement bonus (very small effect)
        if engagement_rate >= 0.08:  # 8%+ engagement
            engagement_multiplier = 1.1
        elif engagement_rate >= 0.04:  # 4%+ engagement
            engagement_multiplier = 1.05
        elif engagement_rate < 0.02:  # <2% engagement
            engagement_multiplier = 0.95
        else:
            engagement_multiplier = 1.0
        
        rpm['avg'] *= engagement_multiplier
        rpm['high'] *= engagement_multiplier
        
        # Seasonality adjustment (Q4 = higher ad spend)
        month = datetime.now().month
        if month in [11, 12]:  # Nov-Dec (Black Friday, Christmas)
            seasonality_multiplier = 1.20
        elif month == 10:  # October
            seasonality_multiplier = 1.10
        elif month in [1, 2]:  # Jan-Feb (post-holiday slump)
            seasonality_multiplier = 0.80
        elif month in [6, 7, 8]:  # Summer (slightly lower)
            seasonality_multiplier = 0.95
        else:
            seasonality_multiplier = 1.0
        
        rpm['low'] *= seasonality_multiplier
        rpm['avg'] *= seasonality_multiplier
        rpm['high'] *= seasonality_multiplier
        
        # Round values
        rpm = {
            'low': round(rpm['low'], 3),
            'avg': round(rpm['avg'], 3),
            'high': round(rpm['high'], 3)
        }
        
        # CPM is roughly RPM / 0.25 (since ~25% of views are monetized at creator's rate)
        # This is just for display purposes
        estimated_cpm = {
            'low': round(rpm['low'] / 0.20, 2),
            'avg': round(rpm['avg'] / 0.25, 2),
            'high': round(rpm['high'] / 0.30, 2)
        }
        
        return {
            'cpm': estimated_cpm,
            'rpm': rpm,
            'niche': niche,
            'region': region,
            'engagement_multiplier': engagement_multiplier,
            'seasonality_multiplier': seasonality_multiplier,
            'video_length_multiplier': length_multiplier,
            'monetization_rate': 0.25  # Approximate % of views that generate revenue
        }
    
    def estimate_earnings(self, stats: Dict, monthly_views_data: Dict = None, videos: List[Dict] = None) -> Dict:
        """
        Estimate monthly earnings based on channel stats and actual monthly views.
        Uses ACTUAL RPM data for more accurate estimates.
        """
        subscriber_count = stats.get('subscriber_count', 0)
        view_count = stats.get('view_count', 0)
        video_count = stats.get('video_count', 0)
        
        # Detect niche and region
        niche = self.detect_channel_niche(stats, videos)
        region = self.get_audience_region(stats)
        
        # Calculate engagement rate (likes/views)
        engagement_rate = 0.04  # default 4%
        avg_video_length = 10  # default 10 minutes
        
        if videos:
            total_views = sum(v.get('view_count', 0) for v in videos[:10])
            total_likes = sum(v.get('like_count', 0) for v in videos[:10])
            if total_views > 0:
                engagement_rate = total_likes / total_views
            
            # Try to estimate average video length from duration if available
            durations = [v.get('duration_minutes', 0) for v in videos[:10] if v.get('duration_minutes', 0) > 0]
            if durations:
                avg_video_length = sum(durations) / len(durations)
        
        # Get RPM calculation with all factors
        rpm_data = self.calculate_rpm(niche, region, engagement_rate, avg_video_length)
        
        # Get estimated monthly views from actual data
        if monthly_views_data and monthly_views_data.get('estimated_monthly_views', 0) > 0:
            estimated_monthly_views = monthly_views_data['estimated_monthly_views']
            calculation_method = monthly_views_data.get('calculation_method', 'data_analysis')
        else:
            # Fallback calculation
            if video_count > 0 and view_count > 0:
                avg_views_per_video = view_count / video_count
                estimated_monthly_views = int(avg_views_per_video * 4)
            elif subscriber_count > 0:
                estimated_monthly_views = int(subscriber_count * 2)
            else:
                estimated_monthly_views = 0
            calculation_method = 'fallback_estimate'
        
        # Calculate earnings using ACTUAL RPM (Revenue Per Mille)
        # Formula: Monthly Views × RPM ÷ 1000
        earnings_low = (estimated_monthly_views * rpm_data['rpm']['low']) / 1000
        earnings_avg = (estimated_monthly_views * rpm_data['rpm']['avg']) / 1000
        earnings_high = (estimated_monthly_views * rpm_data['rpm']['high']) / 1000
        
        # Add some context about the estimate
        region_note = ""
        if region == 'vietnam':
            region_note = "Khán giả VN có CPM rất thấp ($0.1-0.5 CPM, ~$0.02-0.10 RPM thực tế)"
        elif region in ['india', 'indonesia', 'philippines']:
            region_note = "Khán giả SEA/South Asia có CPM thấp"
        elif region in ['us', 'uk', 'canada', 'australia']:
            region_note = "Khán giả Tier 1 có CPM cao"
        
        return {
            'estimated_monthly_views': estimated_monthly_views,
            'monthly_views_data': monthly_views_data or {},
            'calculation_method': calculation_method,
            'niche': niche,
            'niche_vi': self._get_niche_vietnamese(niche),
            'audience_region': region,
            'cpm_range': rpm_data['cpm'],
            'rpm_range': rpm_data['rpm'],
            'cpm_region': self._get_region_vietnamese(region),
            'monetization_rate': rpm_data['monetization_rate'],
            'engagement_rate': round(engagement_rate * 100, 2),
            'seasonality': rpm_data['seasonality_multiplier'],
            'video_length_bonus': rpm_data.get('video_length_multiplier', 1.0),
            'region_note': region_note,
            'earnings_usd': {
                'low': round(earnings_low, 2),
                'average': round(earnings_avg, 2),
                'high': round(earnings_high, 2)
            },
            'earnings_formula': 'Thu nhập = Views × RPM ÷ 1000 (RPM là số tiền thực nhận/1000 views)'
        }
    
    def _get_niche_vietnamese(self, niche: str) -> str:
        """Get Vietnamese name for niche"""
        niche_names = {
            'finance': 'Tài chính',
            'business': 'Kinh doanh',
            'tech': 'Công nghệ',
            'education': 'Giáo dục',
            'health': 'Sức khỏe',
            'gaming': 'Gaming',
            'entertainment': 'Giải trí',
            'music': 'Âm nhạc',
            'lifestyle': 'Lifestyle',
            'food': 'Ẩm thực',
            'travel': 'Du lịch',
            'news': 'Tin tức',
            'kids': 'Thiếu nhi',
            'default': 'Tổng hợp'
        }
        return niche_names.get(niche, 'Tổng hợp')
    
    def _get_region_vietnamese(self, region: str) -> str:
        """Get Vietnamese name for region"""
        region_names = {
            'vietnam': 'Việt Nam',
            'us': 'Hoa Kỳ',
            'uk': 'Anh',
            'canada': 'Canada',
            'australia': 'Úc',
            'germany': 'Đức',
            'japan': 'Nhật Bản',
            'india': 'Ấn Độ',
            'brazil': 'Brazil',
            'indonesia': 'Indonesia',
            'philippines': 'Philippines',
            'thailand': 'Thái Lan',
            'international': 'Quốc tế'
        }
        return region_names.get(region, 'Quốc tế')
    
    # ==================== Main Analysis Method ====================
    
    def analyze_channel(self, url: str) -> Dict:
        """
        Comprehensive channel analysis using all available methods
        Priority: YouTube Data API > Web Scraping > Fallback
        """
        if not url:
            return {'success': False, 'error': 'Vui lòng nhập link kênh YouTube'}
        
        # Parse URL
        identifier = self.parse_youtube_url(url)
        
        if not identifier['value']:
            return {
                'success': False, 
                'error': 'Không thể xác định kênh từ link này. Hãy thử định dạng: @username, youtube.com/@username, hoặc youtube.com/channel/UC...'
            }
        
        logger.info(f"Analyzing channel: {identifier}")
        
        stats = None
        method_used = 'none'
        
        # Method 1: YouTube Data API (most accurate)
        if self.api_key:
            logger.info("Trying YouTube Data API...")
            
            if identifier['type'] == 'channel_id':
                stats = self.get_channel_by_id_api(identifier['value'])
            elif identifier['type'] == 'handle':
                stats = self.get_channel_by_handle_api(identifier['value'])
            elif identifier['type'] == 'legacy_username':
                stats = self.get_channel_by_username_api(identifier['value'])
            else:
                # Try to resolve to channel ID first
                channel_id = self.resolve_to_channel_id(identifier)
                if channel_id:
                    stats = self.get_channel_by_id_api(channel_id)
            
            if stats:
                method_used = 'youtube_api'
                logger.info("Got data from YouTube Data API")
        
        # Method 2: Web Scraping
        if not stats or stats.get('subscriber_count', 0) == 0:
            logger.info("Trying web scraping...")
            channel_url = self._build_channel_url(identifier)
            scraped = self.scrape_channel_page(channel_url)
            
            if scraped:
                if stats:
                    # Merge data
                    for key, value in scraped.items():
                        if value and (not stats.get(key) or stats.get(key) == 0 or stats.get(key) == 'Unknown'):
                            stats[key] = value
                else:
                    stats = scraped
                
                method_used = 'scraping' if method_used == 'none' else method_used + '+scraping'
                logger.info("Got data from scraping")
        
        # Validate results
        if not stats:
            return {
                'success': False,
                'error': 'Không thể lấy thông tin kênh. Vui lòng kiểm tra lại link.'
            }
        
        if stats.get('subscriber_count', 0) == 0 and stats.get('view_count', 0) == 0:
            # Check if hidden
            if stats.get('hidden_subscriber_count'):
                return {
                    'success': False,
                    'error': 'Kênh này đã ẩn số người đăng ký. Không thể ước tính thu nhập.'
                }
            return {
                'success': False,
                'error': 'Không thể lấy số liệu kênh. Kênh có thể không tồn tại hoặc đã ẩn thông tin.'
            }
        
        # Get channel_id for fetching videos
        channel_id = stats.get('channel_id', '')
        if not channel_id:
            channel_id = self.resolve_to_channel_id(identifier)
        
        # Get recent videos to calculate actual monthly views
        recent_videos = []
        if channel_id:
            logger.info(f"Getting recent videos for channel: {channel_id}")
            recent_videos = self.get_recent_videos(channel_id, max_results=30)
            logger.info(f"Found {len(recent_videos)} recent videos")
        
        # Calculate monthly views based on actual data
        monthly_views_data = self.calculate_monthly_views(
            videos=recent_videos,
            total_views=stats.get('view_count', 0),
            video_count=stats.get('video_count', 0),
            channel_created=stats.get('created_at', '')
        )
        
        # Estimate earnings with actual monthly views and video data for better RPM
        earnings = self.estimate_earnings(stats, monthly_views_data, recent_videos)
        
        # Get exchange rate
        exchange_rate = self.get_exchange_rate()
        
        # Convert to VND
        earnings_vnd = {
            'low': round(earnings['earnings_usd']['low'] * exchange_rate),
            'average': round(earnings['earnings_usd']['average'] * exchange_rate),
            'high': round(earnings['earnings_usd']['high'] * exchange_rate)
        }
        
        # AI-Powered Analysis for enhanced accuracy
        ai_analysis = None
        ai_earnings = None
        
        if self.ai_enabled:
            logger.info("Running AI analysis for enhanced accuracy...")
            ai_analysis = self.analyze_with_ai(stats, recent_videos, monthly_views_data)
            
            if ai_analysis:
                ai_earnings = self.get_ai_enhanced_earnings(ai_analysis, earnings, exchange_rate)
                method_used = method_used + '+ai' if method_used != 'none' else 'ai'
                logger.info(f"AI analysis complete. Niche: {ai_analysis.get('niche', 'unknown')}, Confidence: {ai_analysis.get('confidence_score', 0)}%")
        
        # Get current month name
        month_names_vn = ['', 'Tháng 1', 'Tháng 2', 'Tháng 3', 'Tháng 4', 'Tháng 5', 'Tháng 6',
                         'Tháng 7', 'Tháng 8', 'Tháng 9', 'Tháng 10', 'Tháng 11', 'Tháng 12']
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        # Use AI earnings if available and confident, otherwise use base calculation
        final_earnings = earnings
        final_earnings_vnd = earnings_vnd
        
        if ai_earnings and ai_analysis and ai_analysis.get('confidence_score', 0) >= 60:
            final_earnings = {
                'estimated_monthly_views': ai_earnings['estimated_monthly_views'],
                'cpm_range': ai_earnings['cpm_range'],
                'cpm_region': earnings.get('cpm_region', 'Quốc tế'),
                'monetization_rate': {
                    'low': ai_earnings['monetization_rate'] - 0.1,
                    'average': ai_earnings['monetization_rate'],
                    'high': ai_earnings['monetization_rate'] + 0.05
                },
                'earnings_usd': ai_earnings['earnings_usd'],
                'calculation_method': 'ai_analysis',
                'earnings_formula': earnings.get('earnings_formula', '')
            }
            final_earnings_vnd = ai_earnings['earnings_vnd']
        
        result = {
            'success': True,
            'channel': stats,
            'recent_videos': recent_videos[:10],  # Include top 10 recent videos
            'monthly_analysis': {
                'current_month': f"{month_names_vn[current_month]} {current_year}",
                'estimated_monthly_views': final_earnings.get('estimated_monthly_views', earnings.get('estimated_monthly_views', 0)),
                'calculation_method': final_earnings.get('calculation_method', earnings.get('calculation_method', '')),
                'videos_analyzed': monthly_views_data.get('videos_analyzed', 0),
                'videos_last_30_days': monthly_views_data.get('videos_last_30_days', 0),
                'views_last_30_days': monthly_views_data.get('views_last_30_days', 0),
                'avg_views_per_video': monthly_views_data.get('avg_views_per_video', 0),
                'channel_age_months': monthly_views_data.get('channel_age_months', 0),
                'avg_monthly_views_lifetime': monthly_views_data.get('avg_monthly_views_lifetime', 0),
            },
            'earnings': final_earnings,
            'earnings_vnd': final_earnings_vnd,
            'exchange_rate': exchange_rate,
            'method': method_used,
            'analyzed_at': datetime.now().isoformat(),
            'disclaimer': f'Ước tính dựa trên CPM ${final_earnings["cpm_range"]["low"]}-${final_earnings["cpm_range"]["high"]}/1000 views ({final_earnings.get("cpm_region", "Quốc tế")}). Thu nhập thực tế phụ thuộc vào niche, vùng miền người xem, tỷ lệ quảng cáo và nhiều yếu tố khác.'
        }
        
        # Add AI insights if available
        if ai_analysis:
            result['ai_insights'] = {
                'niche': ai_analysis.get('niche', 'unknown'),
                'niche_vi': ai_analysis.get('niche_vi', 'Không xác định'),
                'growth_trend': ai_analysis.get('growth_trend', 'stable'),
                'confidence_score': ai_analysis.get('confidence_score', 0),
                'analysis': ai_analysis.get('analysis', ''),
                'ai_enabled': True
            }
        else:
            result['ai_insights'] = {
                'ai_enabled': False,
                'reason': 'AI analysis not available'
            }
        
        # Check monetization status
        monetization_status = self.check_monetization_status(stats, recent_videos)
        result['monetization'] = monetization_status
        
        return result


# Singleton
_analyzer_instance = None

def get_youtube_analyzer(api_key: str = None) -> YouTubeAnalyzer:
    """Get or create YouTubeAnalyzer instance"""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = YouTubeAnalyzer(api_key)
    return _analyzer_instance
