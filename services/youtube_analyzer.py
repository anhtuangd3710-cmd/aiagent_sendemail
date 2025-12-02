"""
YouTube Channel Analyzer Service
Analyzes YouTube channels and estimates monthly earnings
"""

import re
import logging
import requests
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class YouTubeAnalyzer:
    """Service to analyze YouTube channels and estimate earnings"""
    
    # CPM rates ($ per 1000 views) - varies by niche
    CPM_RATES = {
        'low': 0.5,      # Entertainment, gaming
        'medium': 2.0,   # General content
        'high': 5.0,     # Finance, tech, business
        'average': 2.0   # Default estimate
    }
    
    # Exchange rate API
    EXCHANGE_API = "https://api.exchangerate-api.com/v4/latest/USD"
    
    def __init__(self, api_key: str = None):
        """Initialize with optional YouTube Data API key"""
        self.api_key = api_key
        self.youtube_api_base = "https://www.googleapis.com/youtube/v3"
        
    def extract_channel_id(self, url: str) -> Optional[str]:
        """Extract channel ID or username from YouTube URL"""
        patterns = [
            # /channel/UC... format
            r'youtube\.com/channel/([a-zA-Z0-9_-]+)',
            # /@username format
            r'youtube\.com/@([a-zA-Z0-9_-]+)',
            # /c/customname format
            r'youtube\.com/c/([a-zA-Z0-9_-]+)',
            # /user/username format
            r'youtube\.com/user/([a-zA-Z0-9_-]+)',
            # Direct channel ID
            r'^(UC[a-zA-Z0-9_-]{22})$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def get_exchange_rate(self) -> float:
        """Get current USD to VND exchange rate"""
        try:
            response = requests.get(self.EXCHANGE_API, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('rates', {}).get('VND', 24500)
        except Exception as e:
            logger.warning(f"Could not fetch exchange rate: {e}")
        
        # Default fallback rate
        return 24500
    
    def get_channel_stats_via_api(self, channel_identifier: str) -> Optional[Dict]:
        """Get channel stats using YouTube Data API (if API key available)"""
        if not self.api_key:
            return None
            
        try:
            # First, try to resolve handle/username to channel ID
            if channel_identifier.startswith('@') or not channel_identifier.startswith('UC'):
                # Search for channel
                search_url = f"{self.youtube_api_base}/search"
                params = {
                    'part': 'snippet',
                    'q': channel_identifier,
                    'type': 'channel',
                    'maxResults': 1,
                    'key': self.api_key
                }
                response = requests.get(search_url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('items'):
                        channel_identifier = data['items'][0]['snippet']['channelId']
            
            # Get channel statistics
            stats_url = f"{self.youtube_api_base}/channels"
            params = {
                'part': 'snippet,statistics,brandingSettings',
                'id': channel_identifier,
                'key': self.api_key
            }
            
            response = requests.get(stats_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('items'):
                    item = data['items'][0]
                    stats = item.get('statistics', {})
                    snippet = item.get('snippet', {})
                    
                    return {
                        'channel_id': item.get('id'),
                        'title': snippet.get('title', 'Unknown'),
                        'description': snippet.get('description', '')[:200],
                        'thumbnail': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
                        'subscriber_count': int(stats.get('subscriberCount', 0)),
                        'view_count': int(stats.get('viewCount', 0)),
                        'video_count': int(stats.get('videoCount', 0)),
                        'created_at': snippet.get('publishedAt', ''),
                        'country': snippet.get('country', 'Unknown')
                    }
        except Exception as e:
            logger.error(f"YouTube API error: {e}")
        
        return None
    
    def scrape_channel_stats(self, url: str) -> Optional[Dict]:
        """Scrape channel stats from YouTube page (fallback method)"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                return None
            
            html = response.text
            
            # Extract channel name
            title_match = re.search(r'"channelMetadataRenderer":\{"title":"([^"]+)"', html)
            title = title_match.group(1) if title_match else "Unknown Channel"
            
            # Extract subscriber count
            sub_patterns = [
                r'"subscriberCountText":\{"simpleText":"([^"]+)"',
                r'"subscriberCountText":\{"accessibility":\{"accessibilityData":\{"label":"([^"]+)"',
            ]
            
            subscriber_count = 0
            for pattern in sub_patterns:
                sub_match = re.search(pattern, html)
                if sub_match:
                    sub_text = sub_match.group(1)
                    subscriber_count = self._parse_count(sub_text)
                    break
            
            # Extract video count
            video_match = re.search(r'"videosCountText":\{"runs":\[\{"text":"([^"]+)"', html)
            video_count = 0
            if video_match:
                video_count = self._parse_count(video_match.group(1))
            
            # Extract total views (from about page or estimate)
            view_patterns = [
                r'"viewCountText":\{"simpleText":"([^"]+)"',
                r'viewCount":"(\d+)"',
            ]
            
            view_count = 0
            for pattern in view_patterns:
                view_match = re.search(pattern, html)
                if view_match:
                    view_count = self._parse_count(view_match.group(1))
                    break
            
            # Extract thumbnail
            thumb_match = re.search(r'"avatar":\{"thumbnails":\[\{"url":"([^"]+)"', html)
            thumbnail = thumb_match.group(1) if thumb_match else ""
            
            # Extract description
            desc_match = re.search(r'"description":"([^"]{0,300})"', html)
            description = desc_match.group(1) if desc_match else ""
            
            return {
                'channel_id': self.extract_channel_id(url) or 'unknown',
                'title': title,
                'description': description[:200],
                'thumbnail': thumbnail.replace('\\u0026', '&'),
                'subscriber_count': subscriber_count,
                'view_count': view_count,
                'video_count': video_count,
                'created_at': '',
                'country': 'Unknown'
            }
            
        except Exception as e:
            logger.error(f"Error scraping YouTube channel: {e}")
            return None
    
    def _parse_count(self, text: str) -> int:
        """Parse subscriber/view count from text like '1.5M', '100K', etc."""
        if not text:
            return 0
            
        text = text.upper().replace(',', '').replace(' ', '')
        text = re.sub(r'[^\d.KMB]', '', text)
        
        multipliers = {
            'K': 1000,
            'M': 1000000,
            'B': 1000000000
        }
        
        for suffix, multiplier in multipliers.items():
            if suffix in text:
                try:
                    number = float(text.replace(suffix, ''))
                    return int(number * multiplier)
                except:
                    pass
        
        try:
            return int(float(re.sub(r'[^\d.]', '', text)))
        except:
            return 0
    
    def estimate_monthly_earnings(self, stats: Dict, cpm_type: str = 'average') -> Dict:
        """Estimate monthly earnings based on channel stats"""
        
        view_count = stats.get('view_count', 0)
        video_count = stats.get('video_count', 0)
        subscriber_count = stats.get('subscriber_count', 0)
        
        # Estimate monthly views
        # Average channel gets about 10-30% of total views per month if active
        # We'll estimate based on video count and recency
        if video_count > 0 and view_count > 0:
            avg_views_per_video = view_count / video_count
            # Assume 4-8 videos per month for active channel
            estimated_monthly_views_low = avg_views_per_video * 4 * 0.3  # Conservative
            estimated_monthly_views_high = avg_views_per_video * 8 * 0.7  # Optimistic
            estimated_monthly_views_avg = (estimated_monthly_views_low + estimated_monthly_views_high) / 2
        else:
            # Fallback: estimate based on subscriber count
            # Active channels typically get 10-30% of subscribers as views per video
            estimated_monthly_views_low = subscriber_count * 0.1 * 4
            estimated_monthly_views_high = subscriber_count * 0.3 * 8
            estimated_monthly_views_avg = (estimated_monthly_views_low + estimated_monthly_views_high) / 2
        
        # Get CPM rate
        cpm = self.CPM_RATES.get(cpm_type, self.CPM_RATES['average'])
        cpm_low = self.CPM_RATES['low']
        cpm_high = self.CPM_RATES['high']
        
        # Calculate earnings (CPM is per 1000 views)
        # Only about 40-60% of views are monetized (ads shown)
        monetization_rate = 0.5
        
        earnings_low = (estimated_monthly_views_low * monetization_rate * cpm_low) / 1000
        earnings_high = (estimated_monthly_views_high * monetization_rate * cpm_high) / 1000
        earnings_avg = (estimated_monthly_views_avg * monetization_rate * cpm) / 1000
        
        return {
            'estimated_monthly_views': {
                'low': int(estimated_monthly_views_low),
                'average': int(estimated_monthly_views_avg),
                'high': int(estimated_monthly_views_high)
            },
            'cpm_used': {
                'low': cpm_low,
                'average': cpm,
                'high': cpm_high
            },
            'earnings_usd': {
                'low': round(earnings_low, 2),
                'average': round(earnings_avg, 2),
                'high': round(earnings_high, 2)
            }
        }
    
    def analyze_channel(self, url: str) -> Dict:
        """Main method to analyze a YouTube channel"""
        
        # Validate and normalize URL
        if not url:
            return {'success': False, 'error': 'Vui lòng nhập link kênh YouTube'}
        
        # Add https if missing
        if not url.startswith('http'):
            if url.startswith('@'):
                url = f'https://www.youtube.com/{url}'
            else:
                url = f'https://www.youtube.com/{url}'
        
        # Validate YouTube URL
        if 'youtube.com' not in url and 'youtu.be' not in url:
            return {'success': False, 'error': 'Link không hợp lệ. Vui lòng nhập link kênh YouTube'}
        
        # Extract channel identifier
        channel_id = self.extract_channel_id(url)
        if not channel_id:
            return {'success': False, 'error': 'Không thể xác định kênh từ link này'}
        
        # Try API first, then fallback to scraping
        stats = None
        if self.api_key:
            stats = self.get_channel_stats_via_api(channel_id)
        
        if not stats:
            stats = self.scrape_channel_stats(url)
        
        if not stats:
            return {
                'success': False, 
                'error': 'Không thể lấy thông tin kênh. Vui lòng kiểm tra lại link hoặc thử lại sau.'
            }
        
        # Estimate earnings
        earnings = self.estimate_monthly_earnings(stats)
        
        # Get exchange rate
        exchange_rate = self.get_exchange_rate()
        
        # Convert to VND
        earnings_vnd = {
            'low': round(earnings['earnings_usd']['low'] * exchange_rate),
            'average': round(earnings['earnings_usd']['average'] * exchange_rate),
            'high': round(earnings['earnings_usd']['high'] * exchange_rate)
        }
        
        return {
            'success': True,
            'channel': stats,
            'earnings': earnings,
            'earnings_vnd': earnings_vnd,
            'exchange_rate': exchange_rate,
            'analyzed_at': datetime.now().isoformat(),
            'disclaimer': 'Số liệu chỉ mang tính chất ước tính dựa trên dữ liệu công khai. Thu nhập thực tế có thể khác biệt đáng kể.'
        }


# Singleton instance
_youtube_analyzer = None

def get_youtube_analyzer(api_key: str = None) -> YouTubeAnalyzer:
    """Get or create YouTubeAnalyzer instance"""
    global _youtube_analyzer
    if _youtube_analyzer is None:
        _youtube_analyzer = YouTubeAnalyzer(api_key)
    return _youtube_analyzer
