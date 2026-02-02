from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import time
from datetime import datetime
import random
import hashlib
from urllib.parse import urlparse

DEVELOPER = "ERROR"

app = Flask(__name__)
CORS(app)

# Cache for frequently requested videos
cache = {}
CACHE_TIMEOUT = 300

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
        
        try:
            user_headers = self.get_user_headers()
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'simulate': True,
                'skip_download': True,
                'geturl': True,
                'format': format_type,
                'socket_timeout': 30,
                'extractor_retries': 3,
                'fragment_retries': 10,
                'retries': 10,
                'skip_unavailable_fragments': True,
                'ignoreerrors': True,
                'force_generic_extractor': False,
                'cookiefile': None,
                'http_headers': user_headers,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web'],
                        'player_skip': ['configs'],
                        'skip': ['hls', 'dash']
                    },
                    'instagram': {
                        'web': True,
                        'login': False
                    },
                    'twitter': {
                        'cards': True,
                        'api': 'graphql'
                    },
                    'facebook': {
                        'web': True,
                        'login': False
                    },
                    'tiktok': {
                        'web': True,
                        'app': True
                    }
                }
            }
            
            # Add referer from original URL
            parsed_url = urlparse(url)
            if parsed_url.netloc:
                ydl_opts['http_headers']['Referer'] = f'https://{parsed_url.netloc}'
                ydl_opts['http_headers']['Origin'] = f'https://{parsed_url.netloc}'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                platform = self._detect_platform(url)
                
                if 'entries' in info:
                    return self._process_playlist(info, url, platform, start_time, user_headers)
                else:
                    return self._process_video(info, url, platform, start_time, user_headers)
                
        except Exception as e:
            # Try fallback method for YouTube
            if 'youtube' in url.lower():
                return self._youtube_fallback(url, start_time)
            return error_response(f"Processing failed: {str(e)[:200]}")
    
    def _youtube_fallback(self, url, start_time):
        """Fallback method for YouTube when main method fails"""
        try:
            user_headers = self.get_user_headers()
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'simulate': True,
                'skip_download': True,
                'format': 'worst',
                'socket_timeout': 20,
                'http_headers': user_headers,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android'],
                        'skip': ['hls', 'dash', 'configs']
                    }
                }
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                video_url = info.get('url') or f"https://youtube.com/watch?v={info.get('id')}"
                
                result = {
                    'type': 'video',
                    'platform': 'YouTube',
                    'title': info.get('title', 'YouTube Video'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'video_id': info.get('id'),
                    'note': 'Using fallback method',
                    'processing_time': round(time.time() - start_time, 2),
                    'user_ip_used': self.get_user_ip()
                }
                
                # Cache the result
                cache_key = self.generate_cache_key(url, 'worst')
                cache[cache_key] = (result, time.time())
                
                return success_response(result)
                
        except Exception as e:
            return error_response(f"Fallback failed: {str(e)[:200]}")
    
    def _process_video(self, info, url, platform, start_time, user_headers):
        """Process single video with detailed format information"""
        formats = []
        if 'formats' in info:
            for fmt in info.get('formats', []):
                if fmt.get('url'):
                    format_info = {
                        'format_id': fmt.get('format_id', 'unknown'),
                        'ext': fmt.get('ext', 'mp4'),
                        'resolution': fmt.get('resolution', 'N/A'),
                        'filesize_mb': round(fmt.get('filesize', 0) / (1024*1024), 2) if fmt.get('filesize') else 0,
                        'url': fmt['url'],
                        'vcodec': fmt.get('vcodec', 'unknown'),
                        'acodec': fmt.get('acodec', 'unknown'),
                        'protocol': fmt.get('protocol', 'http'),
                        'has_audio': fmt.get('acodec') != 'none',
                        'has_video': fmt.get('vcodec') != 'none'
                    }
                    
                    # Add additional info
                    if fmt.get('format_note'):
                        format_info['note'] = fmt.get('format_note')
                    if fmt.get('tbr'):
                        format_info['bitrate_kbps'] = fmt.get('tbr')
                    
                    formats.append(format_info)
        
        # Sort by filesize
        formats.sort(key=lambda x: x.get('filesize_mb', 0), reverse=True)
        
        # Get best URLs for different qualities
        best_urls = {}
        for fmt in formats[:5]:  # Top 5 formats
            quality = self._get_quality_label(fmt)
            if quality not in best_urls:
                best_urls[quality] = {
                    'url': fmt['url'],
                    'size_mb': fmt['filesize_mb'],
                    'format_id': fmt['format_id']
                }
        
        result = {
            'type': 'video',
            'platform': platform,
            'title': info.get('title', 'Unknown'),
            'duration': info.get('duration', 0),
            'duration_formatted': self._format_duration(info.get('duration', 0)),
            'thumbnail': info.get('thumbnail'),
            'uploader': info.get('uploader', 'Unknown'),
            'uploader_id': info.get('uploader_id'),
            'view_count': info.get('view_count'),
            'like_count': info.get('like_count'),
            'upload_date': info.get('upload_date'),
            
            # Format information
            'total_formats': len(formats),
            'formats': formats[:10],  # Limit to 10 formats
            'best_urls': best_urls,
            
            # Additional info
            'video_id': info.get('id'),
            'webpage_url': info.get('webpage_url'),
            
            # Technical info
            'processing_time': round(time.time() - start_time, 2),
            'user_ip_used': self.get_user_ip(),
            'headers_used': {k: v for k, v in user_headers.items() if k in ['User-Agent', 'X-Forwarded-For']}
        }
        
        # Cache the result
        cache_key = self.generate_cache_key(url, 'best')
        cache[cache_key] = (result, time.time())
        
        return success_response(result)
    
    def _process_playlist(self, info, url, platform, start_time, user_headers):
        """Process playlist with detailed video information"""
        videos = []
        
        # Limit to 10 videos for cloud deployment
        max_videos = 10
        
        for idx, entry in enumerate(info.get('entries', [])[:max_videos]):
            if entry:
                videos.append({
                    'index': idx + 1,
                    'title': entry.get('title', f'Video {idx+1}'),
                    'duration': entry.get('duration', 0),
                    'duration_formatted': self._format_duration(entry.get('duration', 0)),
                    'uploader': entry.get('uploader', 'Unknown'),
                    'video_id': entry.get('id'),
                    'thumbnail': entry.get('thumbnail'),
                    'view_count': entry.get('view_count')
                })
        
        result = {
            'type': 'playlist',
            'platform': platform,
            'playlist_title': info.get('title', 'Unknown Playlist'),
            'playlist_id': info.get('id'),
            'uploader': info.get('uploader', 'Unknown'),
            'video_count': len(videos),
            'videos': videos,
            'processing_time': round(time.time() - start_time, 2),
            'user_ip_used': self.get_user_ip()
        }
        
        # Cache the result
        cache_key = self.generate_cache_key(url, 'best')
        cache[cache_key] = (result, time.time())
        
        return success_response(result)
    
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
        elif 'tiktok.com' in url_lower:
            return 'TikTok'
        return 'Unknown'
    
    def _get_quality_label(self, fmt):
        """Get quality label"""
        if fmt.get('format_note'):
            return fmt['format_note']
        
        resolution = fmt.get('resolution', '')
        if 'x' in resolution:
            try:
                height = int(resolution.split('x')[1])
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
            except:
                pass
        
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
            "/test": "Test endpoint",
            "/status": "API status"
        },
        "supported_platforms": [
            "YouTube", "Instagram", "TikTok", "Twitter/X", "Facebook"
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
                        'filesize_mb': round(fmt.get('filesize', 0) / (1024*1024), 2) if fmt.get('filesize') else 0,
                        'vcodec': fmt.get('vcodec'),
                        'acodec': fmt.get('acodec'),
                        'protocol': fmt.get('protocol')
                    })
            
            result = {
                'url': url,
                'title': info.get('title'),
                'formats_count': len(formats_list),
                'formats': formats_list[:20],  # Limit to 20 formats
                'your_ip': downloader.get_user_ip()
            }
            
            return jsonify(success_response(result))
            
    except Exception as e:
        return jsonify(error_response(f"Failed to get formats: {str(e)[:200]}")), 500

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
                'thumbnail': info.get('thumbnail'),
                'webpage_url': info.get('webpage_url'),
                'your_ip': downloader.get_user_ip()
            }
            
            return jsonify(success_response(result))
            
    except Exception as e:
        return jsonify(error_response(f"Failed to get info: {str(e)[:200]}")), 500

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
        "timestamp": datetime.utcnow().isoformat()
    })

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify(error_response("Endpoint not found")), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify(error_response("Internal server error")), 500

# This is important for Vercel - it needs the 'app' variable
if __name__ == '__main__':
    app.run(debug=False)