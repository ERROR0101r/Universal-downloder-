from flask import Flask, jsonify, request
import requests
import json
import time
from datetime import datetime

app = Flask(__name__)

# ==================== INSTAGRAM DATA FETCHER ====================
def fetch_instagram_data(session_id):
    """Fetch ALL Instagram data using session ID"""
    
    print(f"\n🔑 Using Session ID: {session_id[:50]}...")
    
    headers = {
        'User-Agent': 'Instagram 309.0.0.28.111 Android (33/13.0; 420dpi; 1080x2260; samsung; SM-A736B; a73xq; qcom; en_US)',
        'X-IG-App-ID': '936619743392459',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.instagram.com/'
    }
    
    cookies = {'sessionid': session_id}
    
    # Main data structure
    data = {
        'success': True,
        'timestamp': datetime.now().isoformat(),
        'account': {},
        'profile': {},
        'posts': [],
        'followers': [],
        'following': [],
        'stories': [],
        'liked_posts': [],
        'comments': [],
        'saved': [],
        'downloads': [],
        'stats': {}
    }
    
    try:
        # 1. Get logged in user info
        print("📱 Fetching account info...")
        resp = requests.get(
            'https://www.instagram.com/api/v1/accounts/current_user/?edit=true',
            headers=headers,
            cookies=cookies,
            timeout=15
        )
        
        if resp.status_code == 200:
            user_data = resp.json().get('user', {})
            data['account'] = {
                'user_id': user_data.get('pk'),
                'username': user_data.get('username'),
                'full_name': user_data.get('full_name'),
                'email': user_data.get('email', 'Not available'),
                'phone': user_data.get('phone_number', 'Not available'),
                'is_private': user_data.get('is_private'),
                'is_verified': user_data.get('is_verified'),
                'is_business': user_data.get('is_business', False),
                'profile_pic': user_data.get('hd_profile_pic_url_info', {}).get('url', ''),
                'bio': user_data.get('biography', ''),
                'website': user_data.get('external_url', ''),
                'followers': user_data.get('follower_count', 0),
                'following': user_data.get('following_count', 0),
                'posts': user_data.get('media_count', 0)
            }
        else:
            return {'error': f'Session invalid. Status: {resp.status_code}'}
        
        # 2. Get profile data
        print("👤 Fetching profile data...")
        resp = requests.get(
            f'https://www.instagram.com/api/v1/users/web_profile_info/?username={data["account"]["username"]}',
            headers=headers,
            cookies=cookies,
            timeout=15
        )
        
        if resp.status_code == 200:
            profile_data = resp.json().get('data', {}).get('user', {})
            data['profile'] = {
                'id': profile_data.get('id'),
                'full_name': profile_data.get('full_name'),
                'category': profile_data.get('category_name', ''),
                'is_professional': profile_data.get('is_professional', False),
                'highlight_count': profile_data.get('highlight_reel_count', 0),
                'has_clips': profile_data.get('has_clips', False),
                'has_guides': profile_data.get('has_guides', False),
                'public_email': profile_data.get('public_email', ''),
                'public_phone': profile_data.get('public_phone_number', ''),
                'whatsapp_linked': profile_data.get('is_whatsapp_linked', False)
            }
        
        # 3. Get posts
        print("📸 Fetching posts...")
        user_id = data['account']['user_id']
        posts = []
        end_cursor = None
        
        for i in range(3):  # Get 3 pages of posts
            params = {
                'query_hash': '69cba40317214236af40e7efa697781d',
                'variables': json.dumps({
                    'id': user_id,
                    'first': 12,
                    'after': end_cursor
                })
            }
            
            resp = requests.get(
                'https://www.instagram.com/graphql/query/',
                headers=headers,
                params=params,
                cookies=cookies,
                timeout=15
            )
            
            if resp.status_code == 200:
                page_data = resp.json()
                edges = page_data.get('data', {}).get('user', {}).get('edge_owner_to_timeline_media', {}).get('edges', [])
                
                for edge in edges:
                    node = edge['node']
                    
                    # Get download URL
                    download_url = ''
                    if node.get('is_video'):
                        if 'video_url' in node:
                            download_url = node['video_url']
                    else:
                        if 'display_resources' in node and node['display_resources']:
                            download_url = node['display_resources'][-1]['src']
                    
                    post = {
                        'id': node['id'],
                        'shortcode': node['shortcode'],
                        'download_url': download_url,
                        'is_video': node.get('is_video', False),
                        'likes': node.get('edge_liked_by', {}).get('count', 0),
                        'comments': node.get('edge_media_to_comment', {}).get('count', 0),
                        'caption': node.get('edge_media_to_caption', {}).get('edges', [{}])[0].get('node', {}).get('text', ''),
                        'timestamp': node.get('taken_at_timestamp', 0),
                        'permalink': f"https://www.instagram.com/p/{node['shortcode']}/"
                    }
                    posts.append(post)
                    
                    if download_url:
                        data['downloads'].append({
                            'type': 'post',
                            'url': download_url,
                            'post_id': node['id']
                        })
                
                # Check for next page
                page_info = page_data.get('data', {}).get('user', {}).get('edge_owner_to_timeline_media', {}).get('page_info', {})
                if page_info.get('has_next_page'):
                    end_cursor = page_info.get('end_cursor')
                else:
                    break
                
                time.sleep(1)  # Rate limiting
            
        data['posts'] = posts
        
        # 4. Get followers
        print("👥 Fetching followers...")
        followers = []
        end_cursor = None
        
        for i in range(2):  # 2 pages of followers
            params = {
                'query_hash': 'c76146de99bb02f6415203be841dd25a',
                'variables': json.dumps({
                    'id': user_id,
                    'first': 24,
                    'after': end_cursor
                })
            }
            
            resp = requests.get(
                'https://www.instagram.com/graphql/query/',
                headers=headers,
                params=params,
                cookies=cookies,
                timeout=15
            )
            
            if resp.status_code == 200:
                page_data = resp.json()
                edges = page_data.get('data', {}).get('user', {}).get('edge_followed_by', {}).get('edges', [])
                
                for edge in edges:
                    follower = {
                        'id': edge['node']['id'],
                        'username': edge['node']['username'],
                        'full_name': edge['node']['full_name'],
                        'profile_pic': edge['node']['profile_pic_url'],
                        'is_verified': edge['node']['is_verified'],
                        'is_private': edge['node']['is_private']
                    }
                    followers.append(follower)
                
                page_info = page_data.get('data', {}).get('user', {}).get('edge_followed_by', {}).get('page_info', {})
                if page_info.get('has_next_page'):
                    end_cursor = page_info.get('end_cursor')
                else:
                    break
                
                time.sleep(1)
        
        data['followers'] = followers
        
        # 5. Get following
        print("👤 Fetching following...")
        following = []
        end_cursor = None
        
        for i in range(2):  # 2 pages of following
            params = {
                'query_hash': 'd04b0a864b4b54837c0d870b0e77e076',
                'variables': json.dumps({
                    'id': user_id,
                    'first': 24,
                    'after': end_cursor
                })
            }
            
            resp = requests.get(
                'https://www.instagram.com/graphql/query/',
                headers=headers,
                params=params,
                cookies=cookies,
                timeout=15
            )
            
            if resp.status_code == 200:
                page_data = resp.json()
                edges = page_data.get('data', {}).get('user', {}).get('edge_follow', {}).get('edges', [])
                
                for edge in edges:
                    follow = {
                        'id': edge['node']['id'],
                        'username': edge['node']['username'],
                        'full_name': edge['node']['full_name'],
                        'profile_pic': edge['node']['profile_pic_url'],
                        'is_verified': edge['node']['is_verified'],
                        'is_private': edge['node']['is_private']
                    }
                    following.append(follow)
                
                page_info = page_data.get('data', {}).get('user', {}).get('edge_follow', {}).get('page_info', {})
                if page_info.get('has_next_page'):
                    end_cursor = page_info.get('end_cursor')
                else:
                    break
                
                time.sleep(1)
        
        data['following'] = following
        
        # 6. Get stories
        print("🎬 Fetching stories...")
        resp = requests.get(
            f'https://i.instagram.com/api/v1/feed/reels_media/?reel_ids={user_id}',
            headers=headers,
            cookies=cookies,
            timeout=15
        )
        
        if resp.status_code == 200:
            stories_data = resp.json()
            if 'reels' in stories_data and str(user_id) in stories_data['reels']:
                reel = stories_data['reels'][str(user_id)]
                for item in reel.get('items', []):
                    story = {
                        'id': item['id'],
                        'is_video': item.get('media_type', 1) == 2,
                        'url': item.get('video_versions', [{}])[0].get('url') if item.get('media_type', 1) == 2 else item.get('image_versions2', {}).get('candidates', [{}])[0].get('url', ''),
                        'timestamp': item.get('taken_at', 0),
                        'expires_at': item.get('expiring_at', 0)
                    }
                    data['stories'].append(story)
                    
                    if 'url' in story and story['url']:
                        data['downloads'].append({
                            'type': 'story',
                            'url': story['url'],
                            'story_id': item['id']
                        })
        
        # 7. Get liked posts
        print("❤️ Fetching liked posts...")
        resp = requests.get(
            'https://www.instagram.com/api/v1/feed/liked/',
            headers=headers,
            cookies=cookies,
            timeout=15
        )
        
        if resp.status_code == 200:
            liked_data = resp.json()
            for item in liked_data.get('items', [])[:20]:  # First 20 liked posts
                liked = {
                    'id': item.get('id'),
                    'shortcode': item.get('code', ''),
                    'username': item.get('user', {}).get('username', ''),
                    'caption': item.get('caption', {}).get('text', '') if item.get('caption') else '',
                    'like_timestamp': item.get('like_ts', 0),
                    'media_url': item.get('image_versions2', {}).get('candidates', [{}])[0].get('url', '')
                }
                data['liked_posts'].append(liked)
        
        # 8. Get saved posts
        print("💾 Fetching saved posts...")
        resp = requests.get(
            'https://i.instagram.com/api/v1/feed/saved/',
            headers=headers,
            cookies=cookies,
            timeout=15
        )
        
        if resp.status_code == 200:
            saved_data = resp.json()
            for item in saved_data.get('items', [])[:15]:  # First 15 saved
                saved = {
                    'id': item.get('id'),
                    'shortcode': item.get('code', ''),
                    'username': item.get('user', {}).get('username', ''),
                    'caption': item.get('caption', {}).get('text', '') if item.get('caption') else ''
                }
                data['saved'].append(saved)
        
        # 9. Get comments
        print("💬 Fetching comments...")
        # Get from user's posts
        for post in data['posts'][:5]:  # First 5 posts
            resp = requests.get(
                f'https://www.instagram.com/api/v1/media/{post["id"]}/comments/',
                headers=headers,
                cookies=cookies,
                timeout=10
            )
            
            if resp.status_code == 200:
                comments_data = resp.json()
                for comment in comments_data.get('comments', [])[:10]:  # First 10 comments per post
                    data['comments'].append({
                        'post_id': post['id'],
                        'comment_id': comment['pk'],
                        'username': comment.get('user', {}).get('username', ''),
                        'text': comment['text'],
                        'timestamp': comment['created_at']
                    })
            
            time.sleep(0.5)
        
        # Add stats
        data['stats'] = {
            'total_posts': len(data['posts']),
            'total_followers': len(data['followers']),
            'total_following': len(data['following']),
            'total_stories': len(data['stories']),
            'total_liked': len(data['liked_posts']),
            'total_saved': len(data['saved']),
            'total_comments': len(data['comments']),
            'total_downloads': len(data['downloads']),
            'processing_time': round(time.time() - start_time, 2)
        }
        
        return data
        
    except Exception as e:
        return {'error': f'API request failed: {str(e)}'}

# ==================== FLASK ROUTES ====================
@app.route('/')
def home():
    return jsonify({
        'api': 'Instagram Complete Data API',
        'version': '1.0',
        'author': 'ERROR',
        'usage': 'GET /sessionid=YOUR_SESSION_ID',
        'example': 'http://localhost:9080/sessionid=123456789:abc123def456...',
        'features': [
            'Complete account info with email/phone',
            'All posts with download links',
            'Followers and following lists',
            'Stories with download links',
            'Liked posts',
            'Saved posts',
            'Comments',
            'JSON response'
        ],
        'note': 'Session ID must be valid and not expired'
    })

@app.route('/sessionid=<session_id>')
def get_instagram_data(session_id):
    """Main endpoint - Get all Instagram data"""
    print(f"\n📥 Request received for session ID")
    
    if not session_id or len(session_id) < 30:
        return jsonify({
            'success': False,
            'error': 'Invalid session ID format',
            'example': '123456789:AbCdEfGhIjKlMnOpQrStUvWxYz:12:xyz...',
            'timestamp': datetime.now().isoformat()
        }), 400
    
    start_time = time.time()
    
    # Fetch data
    data = fetch_instagram_data(session_id)
    
    if 'error' in data:
        return jsonify({
            'success': False,
            'error': data['error'],
            'session_id_preview': session_id[:40] + '...',
            'timestamp': datetime.now().isoformat(),
            'suggestions': [
                'Make sure session ID is not expired',
                'Try getting a fresh session ID',
                'Wait 5-10 minutes if rate limited'
            ]
        }), 401
    
    # Add success and processing time
    data['success'] = True
    data['processing_time_seconds'] = round(time.time() - start_time, 2)
    data['session_id_preview'] = session_id[:30] + '...'
    
    return jsonify(data)

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'endpoints': {
            '/': 'API documentation',
            '/sessionid=<session_id>': 'Get Instagram data',
            '/health': 'Health check'
        }
    })

@app.route('/test/<username>')
def test_public(username):
    """Test endpoint with public data (no session needed)"""
    try:
        resp = requests.get(f'https://www.instagram.com/{username}/?__a=1', timeout=10)
        if resp.status_code == 200:
            return jsonify({
                'success': True,
                'message': 'Public API is working',
                'username': username,
                'status': 'Account exists'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Account not found or private'
            })
    except:
        return jsonify({'success': False, 'error': 'Test failed'})

# ==================== START SERVER ====================
if __name__ == '__main__':
    print("\n" + "="*70)
    print("INSTAGRAM COMPLETE DATA API - SIMPLE GET REQUEST")
    print("="*70)
    print("\n📡 USAGE:")
    print("  Simply add your session ID to the URL:")
    print("  http://localhost:9080/sessionid=YOUR_SESSION_ID")
    
    print("\n🎯 EXAMPLE:")
    print("  http://localhost:9080/sessionid=49700912482:nSBO4UFLiJQa2U:12:AYjDOAYFYdvCo_2y9xUIlSbvbDs3lIZaVMZ0k_KlCQ")
    
    print("\n✨ WHAT YOU GET:")
    print("  ✓ Account info with email/phone")
    print("  ✓ All posts with download links")
    print("  ✓ Followers & following lists")
    print("  ✓ Stories with download links")
    print("  ✓ Liked posts")
    print("  ✓ Saved posts")
    print("  ✓ Comments")
    print("  ✓ Complete JSON response")
    
    print("\n🔧 OTHER ENDPOINTS:")
    print("  • /health - Health check")
    print("  • /test/<username> - Test public account")
    
    print("\n⚠️  IMPORTANT:")
    print("  • Session ID must be fresh (not expired)")
    print("  • Wait 5-10 minutes if rate limited")
    print("  • Processing takes 15-30 seconds")
    
    print("\n🚀 Starting server on port 9080...")
    print("="*70)
    
    app.run(host='0.0.0.0', port=9080, debug=False, threaded=True)