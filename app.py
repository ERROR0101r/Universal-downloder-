import os
import json
import time
import random
import hashlib
from datetime import datetime
from urllib.parse import urlparse
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import yt_dlp

DEVELOPER = "ERROR"

app = Flask(__name__)
CORS(app)

# Cache for frequently requested videos (in-memory for Vercel)
cache = {}
CACHE_TIMEOUT = 300  # 5 minutes

def success_response(data, cache_hit=False):
    response = {
        "success": True,
        "developer": DEVELOPER,
        "timestamp": datetime.utcnow().isoformat(),
        "cache": cache_hit,
        "data": data
    }
    return response

def error_response(message):
    return {
        "success": False,
        "developer": DEVELOPER,
        "timestamp": datetime.utcnow().isoformat(),
        "error": message
    }

class AdvancedCloudDownloader:
    def __init__(self):
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Linux; Android 13; SM-S901U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36'
        ]
        
        # Common proxies (free public proxies)
        self.proxies = [
            None,  # First try without proxy
            'socks5://51.79.50.31:9300',
            'socks5://103.127.1.130:4000',
            'http://45.61.118.199:5836',
            'http://45.95.203.200:4444'
        ]
        
    def get_user_ip(self):
        """Extract user's IP from request headers"""
        ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        if not ip:
            ip = request.headers.get('X-Real-IP', '')
        if not ip:
            ip = request.remote_addr
        return ip or 'unknown'
    
    def get_user_headers(self):
        """Generate headers based on user's IP and request"""
        user_ip = self.get_user_ip()
        user_agent = request.headers.get('User-Agent', random.choice(self.user_agents))
        
        headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'X-Forwarded-For': user_ip,
            'X-Real-IP': user_ip,
            'Referer': 'https://www.google.com/',
            'Origin': 'https://www.google.com'
        }
        
        # Add more headers from original request
        for header in ['Accept-Language', 'Accept-Encoding', 'Cache-Control']:
            if header in request.headers:
                headers[header] = request.headers[header]
        
        return headers
    
    def generate_cache_key(self, url, format_type):
        """Generate cache key for URL"""
        user_ip = self.get_user_ip()
        cache_str = f"{url}_{format_type}_{user_ip}"
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def process_url(self, url, format_type='best'):
        cache_key = self.generate_cache_key(url, format_type)
        
        # Check cache first
        if cache_key in cache:
            cached_data, timestamp = cache[cache_key]
            if time.time() - timestamp < CACHE_TIMEOUT:
                return success_response(cached_data, cache_hit=True)
        
        start_time = time.time()
        
        # Try multiple proxies and methods
        results = []
        for proxy in self.proxies[:3]:  # Try first 3 proxies
            result = self._try_download(url, format_type, proxy)
            if result and result.get('success'):
                results.append(result)
                if len(result['data'].get('formats', [])) > 5:  # Good enough result
                    break
        
        if not results:
            # Try with special extractor args
            result = self._try_special_methods(url, format_type)
            if result and result.get('success'):
                results.append(result)
        
        if results:
            # Select best result (most formats)
            best_result = max(results, key=lambda x: len(x['data'].get('formats', [])) if x.get('data') else 0)
            
            # Cache the result
            cache[cache_key] = (best_result['data'], time.time())
            
            # Add processing time
            best_result['data']['processing_time'] = round(time.time() - start_time, 2)
            best_result['data']['user_ip_used'] = self.get_user_ip()
            
            return best_result
        
        return error_response("All download attempts failed. Try again or use different URL.")
    
    def _try_download(self, url, format_type, proxy=None):
        """Try downloading with specific proxy configuration"""
        try:
            user_headers = self.get_user_headers()
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'simulate': True,
                'skip_download': True,
                'format': format_type,
                'socket_timeout': 25,
                'extractor_retries': 5,
                'fragment_retries': 10,
                'retries': 10,
                'skip_unavailable_fragments': True,
                'ignoreerrors': False,
                'force_generic_extractor': False,
                'cookiefile': None,
                'http_headers': user_headers,
                'proxy': proxy,
                
                # Platform specific settings
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'ios', 'web'],
                        'player_skip': [],
                        'skip': [],
                        'quiet': True
                    },
                    'instagram': {
                        'web': True,
                        'login': False,
                        'story': True
                    },
                    'twitter': {
                        'cards': True,
                        'api': 'graphql',
                        'syndication_api': True
                    },
                    'facebook': {
                        'web': True,
                        'login': False,
                        'sd': True,
                        'hd': True
                    },
                    'tiktok': {
                        'web': True,
                        'app': True
                    }
                },
                
                # Get all formats
                'listformats': True,
                
                # Age restriction bypass (for some platforms)
                'age_limit': 99,
                
                # Add cookies
                'cookiesfrombrowser': ('chrome',) if not proxy else None,
            }
            
            # Add referer from original URL
            parsed_url = urlparse(url)
            if parsed_url.netloc:
                ydl_opts['http_headers']['Referer'] = f'https://{parsed_url.netloc}'
                ydl_opts['http_headers']['Origin'] = f'https://{parsed_url.netloc}'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if 'entries' in info:
                    return self._process_playlist(info, url, start_time, proxy)
                else:
                    return self._process_video(info, url, start_time, proxy, user_headers)
                
        except Exception as e:
            return None
    
    def _try_special_methods(self, url, format_type):
        """Try special methods for difficult platforms"""
        try:
            platform = self._detect_platform(url)
            
            if platform == 'YouTube':
                return self._youtube_special_method(url)
            elif platform == 'Instagram':
                return self._instagram_special_method(url)
            elif platform == 'TikTok':
                return self._tiktok_special_method(url)
            
        except Exception as e:
            return None
        return None
    
    def _process_video(self, info, url, start_time, proxy, user_headers):
        """Process single video with detailed format information"""
        platform = self._detect_platform(url)
        
        # Get ALL available formats
        all_formats = []
        if 'formats' in info:
            for fmt in info.get('formats', []):
                if fmt.get('url') and fmt.get('ext') in ['mp4', 'webm', 'mkv', 'mov']:
                    # Clean and categorize format
                    format_info = {
                        'format_id': fmt.get('format_id', 'unknown'),
                        'ext': fmt.get('ext', 'mp4'),
                        'resolution': self._get_resolution(fmt),
                        'quality': self._get_quality_label(fmt),
                        'filesize_mb': round(fmt.get('filesize', 0) / (1024*1024), 2) if fmt.get('filesize') else 0,
                        'fps': fmt.get('fps'),
                        'vcodec': fmt.get('vcodec', 'unknown').split('.')[0] if fmt.get('vcodec') else 'unknown',
                        'acodec': fmt.get('acodec', 'unknown').split('.')[0] if fmt.get('acodec') else 'unknown',
                        'url': fmt['url'],
                        'protocol': fmt.get('protocol', 'http'),
                        'has_audio': fmt.get('acodec') != 'none',
                        'has_video': fmt.get('vcodec') != 'none',
                        'container': fmt.get('container', 'mp4')
                    }
                    
                    # Add additional info for adaptive formats
                    if fmt.get('format_note'):
                        format_info['note'] = fmt.get('format_note')
                    
                    # Add bitrate if available
                    if fmt.get('tbr'):
                        format_info['bitrate_kbps'] = fmt.get('tbr')
                    
                    all_formats.append(format_info)
        
        # Group formats by quality
        grouped_formats = self._group_formats_by_quality(all_formats)
        
        # Get best URLs for different qualities
        best_urls = self._get_best_urls_by_quality(all_formats)
        
        # Get direct download links
        direct_links = []
        for fmt in all_formats[:10]:  # Limit to 10 formats for response size
            if fmt['protocol'] in ['http', 'https']:
                direct_links.append({
                    'quality': fmt['quality'],
                    'url': fmt['url'],
                    'size_mb': fmt['filesize_mb']
                })
        
        result = {
            'type': 'video',
            'platform': platform,
            'title': info.get('title', 'Unknown'),
            'duration': info.get('duration', 0),
            'duration_formatted': self._format_duration(info.get('duration', 0)),
            'thumbnail': info.get('thumbnail') or info.get('thumbnails', [{}])[0].get('url') if info.get('thumbnails') else None,
            'uploader': info.get('uploader', 'Unknown'),
            'uploader_id': info.get('uploader_id'),
            'view_count': info.get('view_count'),
            'like_count': info.get('like_count'),
            'upload_date': info.get('upload_date'),
            'description': info.get('description', '')[:200] + '...' if info.get('description') else None,
            
            # Format information
            'total_formats': len(all_formats),
            'formats_by_quality': grouped_formats,
            'best_urls': best_urls,
            'direct_links': direct_links[:5],  # Top 5 direct links
            
            # Additional info
            'video_id': info.get('id'),
            'webpage_url': info.get('webpage_url'),
            'categories': info.get('categories', []),
            'tags': info.get('tags', [])[:10],
            
            # Technical info
            'proxy_used': proxy or 'user_ip',
            'headers_used': {k: v for k, v in user_headers.items() if k in ['User-Agent', 'X-Forwarded-For']}
        }
        
        return success_response(result)
    
    def _process_playlist(self, info, url, start_time, proxy):
        """Process playlist with detailed video information"""
        platform = self._detect_platform(url)
        
        videos = []
        for idx, entry in enumerate(info.get('entries', [])):
            if entry and idx < 20:  # Limit to 20 videos
                videos.append({
                    'index': idx + 1,
                    'title': entry.get('title', f'Video {idx+1}'),
                    'duration': entry.get('duration', 0),
                    'duration_formatted': self._format_duration(entry.get('duration', 0)),
                    'uploader': entry.get('uploader', 'Unknown'),
                    'video_id': entry.get('id'),
                    'thumbnail': entry.get('thumbnail'),
                    'view_count': entry.get('view_count'),
                    'url': f"https://youtube.com/watch?v={entry.get('id')}" if entry.get('id') else None
                })
        
        result = {
            'type': 'playlist',
            'platform': platform,
            'playlist_title': info.get('title', 'Unknown Playlist'),
            'playlist_id': info.get('id'),
            'uploader': info.get('uploader', 'Unknown'),
            'video_count': len(videos),
            'videos': videos,
            'proxy_used': proxy or 'user_ip'
        }
        
        return success_response(result)
    
    def _youtube_special_method(self, url):
        """Special method for YouTube"""
        try:
            # Try with mobile user agent and different parameters
            user_headers = self.get_user_headers()
            user_headers['User-Agent'] = 'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'simulate': True,
                'skip_download': True,
                'format': 'best',
                'http_headers': user_headers,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android'],
                        'skip': [],
                        'quiet': True
                    }
                },
                'cookiefile': None
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Try to get manifest URL
                formats = []
                for fmt in info.get('formats', []):
                    if fmt.get('manifest_url'):
                        formats.append({
                            'type': 'manifest',
                            'url': fmt['manifest_url'],
                            'format': 'm3u8',
                            'quality': 'adaptive'
                        })
                    
                    if fmt.get('url') and 'googlevideo.com' in fmt['url']:
                        formats.append({
                            'type': 'direct',
                            'url': fmt['url'],
                            'quality': self._get_quality_label(fmt),
                            'resolution': self._get_resolution(fmt)
                        })
                
                result = {
                    'type': 'video',
                    'platform': 'YouTube',
                    'title': info.get('title', 'YouTube Video'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'special_method': 'mobile_client',
                    'formats': formats,
                    'note': 'Using mobile client method for better access'
                }
                
                return success_response(result)
                
        except Exception as e:
            return None
    
    def _instagram_special_method(self, url):
        """Special method for Instagram"""
        try:
            user_headers = self.get_user_headers()
            user_headers['User-Agent'] = 'Instagram 277.0.0.19.98 Android (28/9.0; 480dpi; 1080x1920; samsung; SM-G973F; beyond1; exynos9820; en_US; 367138953)'
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'simulate': True,
                'skip_download': True,
                'format': 'best',
                'http_headers': user_headers,
                'extractor_args': {
                    'instagram': {
                        'web': True,
                        'login': False,
                        'story': True,
                        'highlights': True
                    }
                }
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                formats = []
                if 'url' in info:
                    formats.append({
                        'type': 'direct',
                        'url': info['url'],
                        'quality': 'best',
                        'ext': 'mp4'
                    })
                
                result = {
                    'type': 'video' if info.get('duration') else 'image',
                    'platform': 'Instagram',
                    'title': info.get('title', 'Instagram Media'),
                    'uploader': info.get('uploader', info.get('owner_username', 'Unknown')),
                    'special_method': 'instagram_app',
                    'formats': formats,
                    'is_reel': 'reel' in url.lower()
                }
                
                return success_response(result)
                
        except Exception as e:
            return None
    
    def _tiktok_special_method(self, url):
        """Special method for TikTok"""
        try:
            user_headers = self.get_user_headers()
            user_headers['User-Agent'] = 'TikTok 26.2.3 rv:262302 (iPhone; iOS 14.6; en_US) Cronet'
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'simulate': True,
                'skip_download': True,
                'format': 'best',
                'http_headers': user_headers,
                'extractor_args': {
                    'tiktok': {
                        'web': True,
                        'app': True
                    }
                }
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                formats = []
                if 'formats' in info:
                    for fmt in info['formats']:
                        if fmt.get('url'):
                            formats.append({
                                'url': fmt['url'],
                                'quality': self._get_quality_label(fmt),
                                'width': fmt.get('width'),
                                'height': fmt.get('height')
                            })
                
                result = {
                    'type': 'video',
                    'platform': 'TikTok',
                    'title': info.get('title', 'TikTok Video'),
                    'author': info.get('uploader', info.get('creator', 'Unknown')),
                    'duration': info.get('duration', 0),
                    'special_method': 'tiktok_app',
                    'formats': formats,
                    'music': info.get('track', info.get('music', 'Unknown'))
                }
                
                return success_response(result)
                
        except Exception as e:
            return None
    
    def _detect_platform(self, url):
        url_lower = url.lower()
        if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            return 'YouTube'
        elif 'instagram.com' in url_lower or 'instagr.am' in url_lower:
            return 'Instagram'
        elif 'twitter.com' in url_lower or 'x.com' in url_lower:
            return 'Twitter/X'
        elif 'facebook.com' in url_lower or 'fb.watch' in url_lower:
            return 'Facebook'
        elif 'tiktok.com' in url_lower or 'tiktok.com' in url_lower:
            return 'TikTok'
        elif 'reddit.com' in url_lower:
            return 'Reddit'
        elif 'likee.video' in url_lower or 'likee.com' in url_lower:
            return 'Likee'
        elif 'snapchat.com' in url_lower:
            return 'Snapchat'
        elif 'pinterest.com' in url_lower:
            return 'Pinterest'
        elif 'twitch.tv' in url_lower:
            return 'Twitch'
        elif 'dailymotion.com' in url_lower:
            return 'DailyMotion'
        elif 'vimeo.com' in url_lower:
            return 'Vimeo'
        return 'Unknown'
    
    def _get_resolution(self, fmt):
        """Extract resolution from format info"""
        if fmt.get('resolution'):
            return fmt['resolution']
        
        width = fmt.get('width')
        height = fmt.get('height')
        if width and height:
            return f"{width}x{height}"
        
        return 'N/A'
    
    def _get_quality_label(self, fmt):
        """Get quality label"""
        if fmt.get('format_note'):
            return fmt['format_note']
        
        height = fmt.get('height')
        if height:
            if height >= 2160:
                return '4K'
            elif height >= 1440:
                return '1440p'
            elif height >= 1080:
                return '1080p'
            elif height >= 720:
                return '720p'
            elif height >= 480:
                return '480p'
            elif height >= 360:
                return '360p'
            elif height >= 240:
                return '240p'
            elif height >= 144:
                return '144p'
        
        return 'unknown'
    
    def _format_duration(self, seconds):
        """Format duration in seconds to HH:MM:SS"""
        if not seconds:
            return "00:00"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    
    def _group_formats_by_quality(self, formats):
        """Group formats by quality"""
        groups = {}
        for fmt in formats:
            quality = fmt['quality']
            if quality not in groups:
                groups[quality] = []
            groups[quality].append({
                'format_id': fmt['format_id'],
                'ext': fmt['ext'],
                'resolution': fmt['resolution'],
                'size_mb': fmt['filesize_mb'],
                'has_audio': fmt['has_audio'],
                'has_video': fmt['has_video']
            })
        
        # Sort qualities
        quality_order = ['4K', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p', 'unknown']
        sorted_groups = {}
        for quality in quality_order:
            if quality in groups:
                sorted_groups[quality] = groups[quality]
        
        return sorted_groups
    
    def _get_best_urls_by_quality(self, formats):
        """Get best URL for each quality"""
        best_urls = {}
        
        # Group by quality
        by_quality = {}
        for fmt in formats:
            quality = fmt['quality']
            if quality not in by_quality:
                by_quality[quality] = []
            by_quality[quality].append(fmt)
        
        # Get best (largest file) for each quality
        for quality, fmt_list in by_quality.items():
            fmt_list.sort(key=lambda x: x['filesize_mb'], reverse=True)
            if fmt_list:
                best = fmt_list[0]
                best_urls[quality] = {
                    'url': best['url'],
                    'size_mb': best['filesize_mb'],
                    'format_id': best['format_id'],
                    'has_audio': best['has_audio'],
                    'has_video': best['has_video']
                }
        
        return best_urls

downloader = AdvancedCloudDownloader()

@app.route('/')
def index():
    return jsonify({
        "developer": DEVELOPER,
        "message": "Advanced Social Media Downloader API",
        "note": "Using user's IP for better access",
        "your_ip": downloader.get_user_ip(),
        "endpoints": {
            "/download": "Download video with details (?url=URL&format=best)",
            "/formats": "Get all available formats (?url=URL)",
            "/info": "Get video info only (?url=URL)",
            "/test": "Test endpoint"
        },
        "supported_platforms": [
            "YouTube", "Instagram", "TikTok", "Twitter/X", "Facebook",
            "Reddit", "Likee", "Snapchat", "Pinterest", "Twitch",
            "DailyMotion", "Vimeo"
        ]
    })

@app.route('/download')
def download():
    """Main download endpoint"""
    url = request.args.get('url')
    if not url:
        return jsonify(error_response("URL parameter is required")), 400
    
    format_type = request.args.get('format', 'best')
    
    result = downloader.process_url(url, format_type)
    return jsonify(result)

@app.route('/formats')
def formats():
    """Get all available formats"""
    url = request.args.get('url')
    if not url:
        return jsonify(error_response("URL parameter is required")), 400
    
    try:
        user_headers = downloader.get_user_headers()
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'simulate': True,
            'skip_download': True,
            'listformats': True,
            'http_headers': user_headers
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats_list = []
            if 'formats' in info:
                for fmt in info['formats']:
                    formats_list.append({
                        'id': fmt.get('format_id'),
                        'ext': fmt.get('ext'),
                        'resolution': fmt.get('resolution'),
                        'fps': fmt.get('fps'),
                        'filesize': fmt.get('filesize'),
                        'vcodec': fmt.get('vcodec'),
                        'acodec': fmt.get('acodec'),
                        'protocol': fmt.get('protocol')
                    })
            
            result = {
                'url': url,
                'title': info.get('title'),
                'formats_count': len(formats_list),
                'formats': formats_list,
                'your_ip': downloader.get_user_ip()
            }
            
            return jsonify(success_response(result))
            
    except Exception as e:
        return jsonify(error_response(f"Failed to get formats: {str(e)}")), 500

@app.route('/info')
def info():
    """Get video info only"""
    url = request.args.get('url')
    if not url:
        return jsonify(error_response("URL parameter is required")), 400
    
    try:
        user_headers = downloader.get_user_headers()
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'simulate': True,
            'skip_download': True,
            'http_headers': user_headers
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            result = {
                'title': info.get('title'),
                'duration': info.get('duration'),
                'uploader': info.get('uploader'),
                'upload_date': info.get('upload_date'),
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
                'description': info.get('description', '')[:500],
                'thumbnail': info.get('thumbnail'),
                'categories': info.get('categories', []),
                'tags': info.get('tags', [])[:10],
                'webpage_url': info.get('webpage_url'),
                'your_ip': downloader.get_user_ip()
            }
            
            return jsonify(success_response(result))
            
    except Exception as e:
        return jsonify(error_response(f"Failed to get info: {str(e)}")), 500

@app.route('/test')
def test():
    """Test endpoint"""
    return jsonify({
        "developer": DEVELOPER,
        "status": "API is running",
        "timestamp": datetime.utcnow().isoformat(),
        "your_ip": downloader.get_user_ip(),
        "user_agent": request.headers.get('User-Agent'),
        "note": "Using your IP address for downloads"
    })

@app.route('/status')
def status():
    """API status"""
    return jsonify({
        "status": "online",
        "developer": DEVELOPER,
        "cache_size": len(cache),
        "timestamp": datetime.utcnow().isoformat(),
        "server_time": time.time()
    })

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify(error_response("Endpoint not found")), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify(error_response("Internal server error")), 500

@app.errorhandler(429)
def ratelimit_error(e):
    return jsonify(error_response("Rate limit exceeded. Try again later.")), 429

# Vercel handler
def handler(event, context):
    """Vercel serverless handler"""
    from vercel_app.wsgi import app
    return app(event, context)

if __name__ == '__main__':
    print(f"🚀 Advanced Social Media Downloader API by {DEVELOPER}")
    print(f"🌐 Running locally: http://127.0.0.1:5000")
    print(f"📱 Using user IP for better platform access")
    print("✅ Supported platforms: YouTube, Instagram, TikTok, Twitter/X, Facebook, Reddit, etc.")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)