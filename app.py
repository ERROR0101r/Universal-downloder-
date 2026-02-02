from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import time
from datetime import datetime
import random
import hashlib
from urllib.parse import urlparse
import os

DEVELOPER = "ERRIOR"

app = Flask(__name__)

# Configure CORS for Vercel
CORS(app, origins=["*"], methods=["GET", "POST"], allow_headers=["*"])

# Cache for frequently requested videos (simplified for Vercel)
cache = {}
CACHE_TIMEOUT = 300
MAX_CACHE_SIZE = 50  # Lower for Vercel serverless

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

def cleanup_cache():
    """Clean up old cache entries"""
    current_time = time.time()
    keys_to_remove = []
    
    # Remove expired cache
    for key, (_, timestamp) in cache.items():
        if current_time - timestamp > CACHE_TIMEOUT:
            keys_to_remove.append(key)
    
    # Remove if cache too large
    if len(cache) > MAX_CACHE_SIZE:
        # Sort by timestamp (oldest first)
        sorted_keys = sorted(cache.keys(), key=lambda k: cache[k][1])
        keys_to_remove.extend(sorted_keys[:20])
    
    # Remove duplicates and delete
    keys_to_remove = list(set(keys_to_remove))
    for key in keys_to_remove:
        del cache[key]

class AdvancedCloudDownloader:
    def __init__(self):
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]
        
    def get_user_ip(self):
        """Extract user's IP from request headers (Vercel compatible)"""
        ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        if not ip:
            ip = request.headers.get('X-Real-IP', '')
        return ip or 'unknown'
    
    def get_user_headers(self):
        """Generate headers"""
        user_ip = self.get_user_ip()
        user_agent = request.headers.get('User-Agent', random.choice(self.user_agents))
        
        headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Cache-Control': 'max-age=0'
        }
        
        return headers
    
    def generate_cache_key(self, url, format_type):
        """Generate cache key for URL"""
        cache_str = f"{url}_{format_type}"
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def process_url(self, url, format_type='best'):
        # Validate URL
        if not url or '://' not in url:
            return error_response("Invalid URL format")
        
        cache_key = self.generate_cache_key(url, format_type)
        
        # Check cache first
        if cache_key in cache:
            cached_data, timestamp = cache[cache_key]
            if time.time() - timestamp < CACHE_TIMEOUT:
                return success_response(cached_data, cache_hit=True)
        
        start_time = time.time()
        
        try:
            user_headers = self.get_user_headers()
            
            # Simplified YT-DLP options for Vercel compatibility
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'simulate': True,
                'skip_download': True,
                'format': format_type,
                'socket_timeout': 10,
                'extractor_retries': 1,
                'retries': 2,
                'ignoreerrors': True,
                'http_headers': user_headers,
                'cachedir': False,
                'no_color': True,
                'no_call_home': True,
                'no_check_certificate': True,
                'verbose': False
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return error_response("No video information found")
                
                if 'entries' in info and info['entries']:
                    return self._process_playlist(info, url, start_time)
                else:
                    return self._process_video(info, url, start_time)
                
        except yt_dlp.utils.DownloadError as e:
            if 'Unsupported URL' in str(e):
                return error_response("Unsupported URL or platform")
            return error_response("Download error")
        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 80:
                error_msg = error_msg[:80] + "..."
            return error_response(f"Processing error: {error_msg}")
    
    def _process_video(self, info, url, start_time):
        """Process single video"""
        formats = []
        if 'formats' in info:
            for fmt in info.get('formats', [])[:8]:  # Limit formats
                if fmt.get('url'):
                    format_info = {
                        'format_id': fmt.get('format_id', 'unknown'),
                        'ext': fmt.get('ext', 'mp4'),
                        'resolution': fmt.get('resolution', 'N/A'),
                        'filesize_mb': round(fmt.get('filesize', 0) / (1024*1024), 2) if fmt.get('filesize') else 0,
                        'url': fmt['url']
                    }
                    formats.append(format_info)
        
        # Sort by filesize
        formats.sort(key=lambda x: x.get('filesize_mb', 0), reverse=True)
        
        result = {
            'type': 'video',
            'platform': self._detect_platform(url),
            'title': info.get('title', 'Unknown'),
            'duration': info.get('duration', 0),
            'duration_formatted': self._format_duration(info.get('duration', 0)),
            'thumbnail': info.get('thumbnail'),
            'uploader': info.get('uploader', 'Unknown'),
            'formats': formats[:3],  # Limit to 3 formats for Vercel
            'webpage_url': info.get('webpage_url'),
            'processing_time': round(time.time() - start_time, 2),
        }
        
        # Cache the result
        cache_key = self.generate_cache_key(url, 'best')
        cache[cache_key] = (result, time.time())
        cleanup_cache()
        
        return success_response(result)
    
    def _process_playlist(self, info, url, start_time):
        """Process playlist"""
        videos = []
        
        # Limit to 3 videos for Vercel
        for idx, entry in enumerate(info.get('entries', [])[:3]):
            if entry:
                videos.append({
                    'index': idx + 1,
                    'title': entry.get('title', f'Video {idx+1}')[:50],
                    'duration': entry.get('duration', 0),
                    'video_id': entry.get('id'),
                })
        
        result = {
            'type': 'playlist',
            'platform': self._detect_platform(url),
            'playlist_title': info.get('title', 'Unknown Playlist')[:100],
            'video_count': len(videos),
            'videos': videos,
            'processing_time': round(time.time() - start_time, 2),
        }
        
        # Cache the result
        cache_key = self.generate_cache_key(url, 'best')
        cache[cache_key] = (result, time.time())
        cleanup_cache()
        
        return success_response(result)
    
    def _detect_platform(self, url):
        url_lower = url.lower()
        if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            return 'YouTube'
        elif 'instagram.com' in url_lower:
            return 'Instagram'
        elif 'tiktok.com' in url_lower:
            return 'TikTok'
        elif 'twitter.com' in url_lower or 'x.com' in url_lower:
            return 'Twitter/X'
        elif 'facebook.com' in url_lower:
            return 'Facebook'
        return 'Other'
    
    def _format_duration(self, seconds):
        """Format duration in seconds to MM:SS or HH:MM:SS"""
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
    """Homepage"""
    return jsonify({
        "developer": DEVELOPER,
        "message": "Social Media Downloader API",
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "download": "/download?url=YOUR_URL",
            "formats": "/formats?url=YOUR_URL",
            "info": "/info?url=YOUR_URL",
            "test": "/test"
        },
        "example": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    })

@app.route('/download')
def download():
    """Main download endpoint"""
    url = request.args.get('url')
    if not url:
        return jsonify(error_response("URL parameter is required")), 400
    
    format_type = request.args.get('format', 'best')
    
    try:
        result = downloader.process_url(url, format_type)
        return jsonify(result)
    except Exception as e:
        return jsonify(error_response("Internal server error")), 500

@app.route('/formats')
def formats():
    """Get available formats"""
    url = request.args.get('url')
    if not url:
        return jsonify(error_response("URL parameter is required")), 400
    
    try:
        user_headers = downloader.get_user_headers()
        
        ydl_opts = {
            'quiet': True,
            'simulate': True,
            'skip_download': True,
            'http_headers': user_headers,
            'listformats': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats_list = []
            if 'formats' in info:
                for fmt in info['formats'][:6]:  # Limit
                    formats_list.append({
                        'id': fmt.get('format_id'),
                        'ext': fmt.get('ext'),
                        'resolution': fmt.get('resolution'),
                        'filesize_mb': round(fmt.get('filesize', 0) / (1024*1024), 2) if fmt.get('filesize') else 0,
                    })
            
            result = {
                'url': url,
                'title': info.get('title'),
                'formats': formats_list,
            }
            
            return jsonify(success_response(result))
            
    except Exception as e:
        return jsonify(error_response("Failed to get formats")), 500

@app.route('/info')
def info():
    """Get video info"""
    url = request.args.get('url')
    if not url:
        return jsonify(error_response("URL parameter is required")), 400
    
    try:
        user_headers = downloader.get_user_headers()
        
        ydl_opts = {
            'quiet': True,
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
                'view_count': info.get('view_count'),
                'thumbnail': info.get('thumbnail'),
                'platform': downloader._detect_platform(url)
            }
            
            return jsonify(success_response(result))
            
    except Exception as e:
        return jsonify(error_response("Failed to get info")), 500

@app.route('/test')
def test():
    """Test endpoint"""
    return jsonify({
        "status": "active",
        "developer": DEVELOPER,
        "timestamp": datetime.utcnow().isoformat(),
        "environment": os.getenv('VERCEL_ENV', 'development'),
        "cache_size": len(cache)
    })

@app.route('/clear-cache')
def clear_cache():
    """Clear cache endpoint"""
    global cache
    cache.clear()
    return jsonify({
        "success": True,
        "message": "Cache cleared",
        "timestamp": datetime.utcnow().isoformat()
    })

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify(error_response("Endpoint not found. Try / for available endpoints")), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify(error_response("Internal server error")), 500

@app.errorhandler(400)
def bad_request(e):
    return jsonify(error_response("Bad request. Check your parameters")), 400

# This is needed for Vercel
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=3000)