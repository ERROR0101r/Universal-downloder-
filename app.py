from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import time
from datetime import datetime
import random
from urllib.parse import urlparse

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
            'X-Forwarded-For': user_ip,
            'X-Real-IP': user_ip,
        }
        return headers
    
    def get_direct_url(self, url):
        """Get direct video URL using user's IP"""
        try:
            user_headers = self.get_user_headers()
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'simulate': True,
                'skip_download': True,
                'format': 'best[ext=mp4]',
                'socket_timeout': 10,
                'retries': 3,
                'ignoreerrors': True,
                'http_headers': user_headers,
                'cookiefile': None,
                'no_color': True,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android'],
                    }
                }
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Check if info is not None
                if not info:
                    return None, "Failed to extract video information"
                
                # Get the best format URL
                if 'url' in info:
                    return info['url'], info.get('title', 'Video')
                
                # Try to get from formats
                if 'formats' in info and info['formats']:
                    for fmt in info['formats']:
                        if fmt.get('url') and fmt.get('ext') == 'mp4':
                            return fmt['url'], info.get('title', 'Video')
                
                return None, "No direct URL found"
                
        except Exception as e:
            return None, str(e)

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
            "direct": "/direct?url=YOUTUBE_URL",
            "info": "/info?url=YOUTUBE_URL"
        },
        "example": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    })

@app.route('/download')
def download():
    """Download video - SIMPLIFIED"""
    url = request.args.get('url')
    if not url:
        return jsonify(error_response("URL parameter is required")), 400
    
    try:
        user_headers = downloader.get_user_headers()
        
        # SIMPLER yt-dlp options
        ydl_opts = {
            'quiet': True,
            'simulate': True,
            'skip_download': True,
            'format': 'best',
            'http_headers': user_headers,
            'ignoreerrors': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # FIX: Check if info is None
            if info is None:
                return jsonify(error_response("Could not fetch video information. The video might be private or unavailable.")), 404
            
            # FIX: Check if 'formats' exists before iterating
            formats = []
            if 'formats' in info and info['formats']:
                for fmt in info.get('formats', [])[:3]:
                    if fmt and 'url' in fmt:
                        formats.append({
                            'format_id': fmt.get('format_id', 'N/A'),
                            'ext': fmt.get('ext', 'mp4'),
                            'resolution': fmt.get('resolution', 'N/A'),
                            'url': fmt['url']
                        })
            
            result = {
                'title': info.get('title', 'Unknown'),
                'url': info.get('webpage_url', url),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'your_ip': downloader.get_user_ip(),
                'formats': formats
            }
            
            # Try to get a direct URL
            if formats:
                result['direct_url'] = formats[0]['url']
            
            return jsonify(success_response(result))
            
    except yt_dlp.utils.DownloadError as e:
        return jsonify(error_response(f"Download error: {str(e)[:100]}")), 400
    except Exception as e:
        return jsonify(error_response(f"Server error: {str(e)[:100]}")), 500

@app.route('/direct')
def direct():
    """Get direct download URL only"""
    url = request.args.get('url')
    if not url:
        return jsonify(error_response("URL parameter is required")), 400
    
    direct_url, title = downloader.get_direct_url(url)
    
    if direct_url:
        return jsonify(success_response({
            'direct_url': direct_url,
            'title': title,
            'your_ip': downloader.get_user_ip()
        }))
    else:
        return jsonify(error_response(f"Failed to get direct URL: {title}")), 400

@app.route('/info')
def info():
    """Get basic video info"""
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
            'ignoreerrors': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # FIX: Check if info is None
            if info is None:
                return jsonify(error_response("Video not found or private")), 404
            
            result = {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count'),
                'thumbnail': info.get('thumbnail'),
                'your_ip': downloader.get_user_ip()
            }
            
            return jsonify(success_response(result))
            
    except Exception as e:
        return jsonify(error_response(f"Failed: {str(e)[:100]}")), 500

@app.route('/test')
def test():
    """Test endpoint"""
    user_ip = downloader.get_user_ip()
    return jsonify({
        "status": "API is running",
        "your_ip": user_ip,
        "timestamp": datetime.utcnow().isoformat(),
        "headers_received": {
            'X-Forwarded-For': request.headers.get('X-Forwarded-For'),
            'X-Real-IP': request.headers.get('X-Real-IP'),
            'User-Agent': request.headers.get('User-Agent')[:50] + '...' if request.headers.get('User-Agent') else None
        }
    })

@app.route('/health')
def health():
    """Health check for Vercel"""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify(error_response("Endpoint not found")), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify(error_response("Internal server error")), 500

# This is needed for Vercel
if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=3000)