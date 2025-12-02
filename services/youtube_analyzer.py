"""
YouTube Channel Analyzer Service
Comprehensive analysis using multiple methods:
1. YouTube Data API v3 (official, requires API key)
2. YouTube oEmbed API (free, limited data)  
3. Noembed API (free proxy)
4. Web scraping with ytInitialData extraction
5. Third-party APIs (SocialBlade style)
"""

import re
import json
import logging
import requests
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from urllib.parse import quote, urlparse, parse_qs
import os

logger = logging.getLogger(__name__)


class YouTubeAnalyzer:
    """Comprehensive YouTube channel analyzer using multiple data sources"""
    
    # CPM rates by region/niche (USD per 1000 monetized views)
    CPM_RATES = {
        'gaming': {'low': 1.0, 'avg': 2.5, 'high': 4.0},
        'entertainment': {'low': 0.5, 'avg': 2.0, 'high': 4.0},
        'education': {'low': 2.0, 'avg': 5.0, 'high': 10.0},
        'tech': {'low': 2.0, 'avg': 6.0, 'high': 12.0},
        'finance': {'low': 5.0, 'avg': 12.0, 'high': 25.0},
        'music': {'low': 0.5, 'avg': 1.5, 'high': 3.0},
        'default': {'low': 1.0, 'avg': 3.0, 'high': 6.0},
        'vietnam': {'low': 0.3, 'avg': 1.0, 'high': 2.5},  # Vietnamese channels
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
            'source': 'youtube_api'
        }
    
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
    
    def estimate_earnings(self, stats: Dict) -> Dict:
        """Estimate monthly earnings based on channel stats"""
        subscriber_count = stats.get('subscriber_count', 0)
        view_count = stats.get('view_count', 0)
        video_count = stats.get('video_count', 0)
        country = stats.get('country', 'Unknown')
        
        # Determine CPM based on country
        cpm_key = 'vietnam' if country.lower() in ['vn', 'vietnam', 'việt nam'] else 'default'
        cpm = self.CPM_RATES[cpm_key]
        
        # Estimate monthly views
        if video_count > 0 and view_count > 0:
            avg_views_per_video = view_count / video_count
            # Estimate 2-8 videos per month
            monthly_views_low = avg_views_per_video * 2
            monthly_views_avg = avg_views_per_video * 4
            monthly_views_high = avg_views_per_video * 8
        elif subscriber_count > 0:
            # Estimate based on subscribers (typically 5-20% engagement)
            monthly_views_low = subscriber_count * 0.5
            monthly_views_avg = subscriber_count * 2
            monthly_views_high = subscriber_count * 5
        else:
            monthly_views_low = monthly_views_avg = monthly_views_high = 0
        
        # Calculate earnings (only ~50% of views are monetized)
        monetization_rate = 0.5
        
        earnings_low = (monthly_views_low * monetization_rate * cpm['low']) / 1000
        earnings_avg = (monthly_views_avg * monetization_rate * cpm['avg']) / 1000
        earnings_high = (monthly_views_high * monetization_rate * cpm['high']) / 1000
        
        return {
            'estimated_monthly_views': {
                'low': int(monthly_views_low),
                'average': int(monthly_views_avg),
                'high': int(monthly_views_high)
            },
            'cpm_range': cpm,
            'earnings_usd': {
                'low': round(earnings_low, 2),
                'average': round(earnings_avg, 2),
                'high': round(earnings_high, 2)
            }
        }
    
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
                
                method_used = 'scraping' if not method_used else method_used + '+scraping'
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
        
        # Estimate earnings
        earnings = self.estimate_earnings(stats)
        
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
            'method': method_used,
            'analyzed_at': datetime.now().isoformat(),
            'disclaimer': f'Ước tính dựa trên CPM ${earnings["cpm_range"]["low"]}-${earnings["cpm_range"]["high"]}/1000 views. Thu nhập thực tế phụ thuộc vào niche, vùng miền người xem, tỷ lệ quảng cáo và nhiều yếu tố khác.'
        }


# Singleton
_analyzer_instance = None

def get_youtube_analyzer(api_key: str = None) -> YouTubeAnalyzer:
    """Get or create YouTubeAnalyzer instance"""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = YouTubeAnalyzer(api_key)
    return _analyzer_instance
