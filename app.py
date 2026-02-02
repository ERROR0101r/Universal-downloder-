from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import time
from datetime import datetime
import random

app = Flask(__name__)
CORS(app)

class UserIPDownloader:
    def __init__(self):
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
    
    def get_user_ip(self):
        """Get user's real IP from Vercel headers"""
        ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        if not ip:
            ip = request.headers.get('X-Real-IP', '')
        return ip or request.remote_addr or 'unknown'
    
    def get_user_headers(self):
        """Generate headers with user's IP and User-Agent"""
        user_ip = self.get_user_ip()
        user_agent = request.headers.get('User-Agent', random.choice(self.user_agents))
        
        headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            # Add user IP to headers to avoid bot detection
            'X-Forwarded-For': user_ip,
            'X-Real-IP': user_ip,
            'X-Client-IP': user_ip,
            'CF-Connecting-IP': user_ip,
            'True-Client-IP': user_ip
        }
        return headers

downloader = UserIPDownloader()

def success_response(data):
    return {
        "success": True,
        "timestamp": datetime.utcnow().isoformat(),
        "data": data
    }

def error_response(message):
    return {
        "success": False,
        "timestamp": datetime.utcnow().isoformat(),
        "error": message
    }

@app.route('/')
def index():
    user_ip = downloader.get_user_ip()
    return jsonify({
        "message": "Social Media Downloader API",
        "your_ip": user_ip,
        "note": "Using YOUR IP address to avoid bot detection",
        "endpoints": {
            "download": "/download?url=YOUTUBE_URL",
            "formats": "/formats?url=YOUTUBE_URL",
            "info": "/info?url=YOUTUBE_URL"
        },
        "example": "/download?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    })

@app.route('/download')
def download():
    """Download video - USING USER'S IP"""
    url = request.args.get('url')
    if not url:
        return jsonify(error_response("URL parameter is required")), 400
    
    format_type = request.args.get('format', 'best')
    
    try:
        # Get user's headers with their IP
        user_headers = downloader.get_user_headers()
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'simulate': True,
            'skip_download': True,
            'format': format_type,
            'socket_timeout': 15,
            'extractor_retries': 2,
            'retries': 3,
            'ignoreerrors': False,
            'http_headers': user_headers,
            'cookiefile': None,
            'no_color': True,
            'no_call_home': True,
            'no_check_certificate': True,
            'verbose': False,
            # YouTube specific settings
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'player_skip': ['configs']
                }
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Get direct video URL
            formats = []
            if 'formats' in info:
                for fmt in info.get('formats', []):
                    if fmt.get('url'):
                        formats.append({
                            'format_id': fmt.get('format_id'),
                            'ext': fmt.get('ext'),
                            'resolution': fmt.get('resolution'),
                            'url': fmt['url'],
                            'filesize_mb': round(fmt.get('filesize', 0) / (1024*1024), 2) if fmt.get('filesize') else 0
                        })
            
            result = {
                'title': info.get('title', 'Unknown'),
                'url': info.get('webpage_url', url),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'user_ip_used': downloader.get_user_ip(),
                'formats': formats[:5],  # Limit to 5 formats
                'direct_url': formats[0]['url'] if formats else None
            }
            
            return jsonify(success_response(result))
            
    except Exception as e:
        error_msg = str(e)
        # Try fallback without extractor args
        try:
            return fallback_download(url, downloader)
        except:
            return jsonify(error_response(f"Error: {error_msg[:100]}")), 500

def fallback_download(url, downloader):
    """Fallback method if main method fails"""
    user_headers = downloader.get_user_headers()
    
    ydl_opts = {
        'quiet': True,
        'simulate': True,
        'skip_download': True,
        'format': 'best[ext=mp4]',
        'http_headers': user_headers
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        
        result = {
            'title': info.get('title', 'Unknown'),
            'url': info.get('webpage_url', url),
            'thumbnail': info.get('thumbnail'),
            'duration': info.get('duration', 0),
            'uploader': info.get('uploader', 'Unknown'),
            'user_ip_used': downloader.get_user_ip(),
            'note': 'Using fallback method'
        }
        
        return jsonify(success_response(result))

@app.route('/formats')
def formats():
    """Get all available formats - USING USER'S IP"""
    url = request.args.get('url')
    if not url:
        return jsonify(error_response("URL parameter is required")), 400
    
    try:
        user_headers = downloader.get_user_headers()
        
        ydl_opts = {
            'quiet': True,
            'simulate': True,
            'skip_download': True,
            'listformats': True,
            'http_headers': user_headers,
            'ignoreerrors': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            formats_list = []
            if 'formats' in info:
                for fmt in info['formats']:
                    if fmt.get('url'):
                        formats_list.append({
                            'id': fmt.get('format_id'),
                            'ext': fmt.get('ext'),
                            'resolution': fmt.get('resolution'),
                            'filesize_mb': round(fmt.get('filesize', 0) / (1024*1024), 2) if fmt.get('filesize') else 0,
                            'url': fmt['url'],
                            'vcodec': fmt.get('vcodec'),
                            'acodec': fmt.get('acodec')
                        })
            
            result = {
                'title': info.get('title'),
                'url': url,
                'your_ip': downloader.get_user_ip(),
                'formats_count': len(formats_list),
                'formats': formats_list[:10]  # Limit to 10 formats
            }
            
            return jsonify(success_response(result))
            
    except Exception as e:
        return jsonify(error_response(f"Failed: {str(e)[:100]}")), 500

@app.route('/info')
def info():
    """Get video info - USING USER'S IP"""
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
                'like_count': info.get('like_count'),
                'thumbnail': info.get('thumbnail'),
                'webpage_url': info.get('webpage_url'),
                'your_ip': downloader.get_user_ip()
            }
            
            return jsonify(success_response(result))
            
    except Exception as e:
        return jsonify(error_response(f"Failed: {str(e)[:100]}")), 500

@app.route('/test')
def test():
    """Test endpoint to show your IP"""
    user_ip = downloader.get_user_ip()
    return jsonify({
        "status": "API is running",
        "your_ip": user_ip,
        "user_agent": request.headers.get('User-Agent'),
        "headers_used": {
            'X-Forwarded-For': request.headers.get('X-Forwarded-For'),
            'X-Real-IP': request.headers.get('X-Real-IP')
        },
        "note": "This IP will be used for all downloads to avoid bot detection"
    })

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify(error_response("Endpoint not found")), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify(error_response("Internal server error")), 500

# This is needed for Vercel
if __name__ == '__main__':
    app.run(debug=False)