# app.py
from flask import Flask, render_template, request, jsonify
import requests
from urllib.parse import quote
import json
import time
import os
from datetime import datetime

app = Flask(__name__)

# ================= CONFIGURATION =================
API_BASE = "https://api.sansekai.my.id/api"

# Environment variable configuration
MAX_PAGES = int(os.environ.get('MAX_PAGES', 30))  # Default 30, bisa diubah via env
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', 3))
RETRY_DELAY = float(os.environ.get('RETRY_DELAY', 2.0))
REQUEST_DELAY = float(os.environ.get('REQUEST_DELAY', 0.5))
MAX_CACHE_SIZE = int(os.environ.get('MAX_CACHE_SIZE', 5000))  # Batas maksimal cache
FLASK_DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

# Cache untuk menyimpan semua anime
anime_cache = []
cache_loaded = False
cache_last_updated = None
cache_loading = False  # Flag untuk mencegah multiple loading

# ================= HELPER FUNCTIONS =================

def debug_response(endpoint, data):
    """Print response untuk debugging (hanya di debug mode)"""
    if FLASK_DEBUG:
        print(f"\n{'='*50}")
        print(f"Endpoint: {endpoint}")
        print(f"Response Type: {type(data)}")
        if isinstance(data, list) and len(data) > 0:
            print(f"First item keys: {data[0].keys() if isinstance(data[0], dict) else 'Not a dict'}")
        elif isinstance(data, dict):
            print(f"Keys: {list(data.keys())[:10]}...")
        print(f"{'='*50}\n")

def safe_api_request(url, retry_count=0):
    """Fungsi aman untuk request API dengan retry mechanism"""
    try:
        # Add headers to mimic browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://sansekai.my.id/'
        }
        
        response = requests.get(url, headers=headers, timeout=10)  # Reduced from 15
        
        # Handle rate limiting (429)
        if response.status_code == 429:
            if retry_count < MAX_RETRIES:
                wait_time = RETRY_DELAY * (retry_count + 1)
                print(f"⚠️  Rate limited (429). Waiting {wait_time}s before retry {retry_count + 1}/{MAX_RETRIES}...")
                time.sleep(wait_time)
                return safe_api_request(url, retry_count + 1)
            else:
                print(f"❌ Max retries reached for rate limiting: {url}")
                return None
        
        # Handle 404 - Endpoint not found
        if response.status_code == 404:
            if FLASK_DEBUG:
                print(f"⚠️  Endpoint not found (404): {url}")
            return None
        
        # Handle other status codes
        if response.status_code != 200:
            if FLASK_DEBUG:
                print(f"⚠️  API request returned status {response.status_code}: {url}")
            return None
        
        return response
        
    except requests.exceptions.Timeout:
        if retry_count < MAX_RETRIES:
            wait_time = RETRY_DELAY * (retry_count + 1)
            print(f"⏰ Timeout. Waiting {wait_time}s before retry {retry_count + 1}/{MAX_RETRIES}...")
            time.sleep(wait_time)
            return safe_api_request(url, retry_count + 1)
        else:
            print(f"❌ Max retries reached for timeout: {url}")
            return None
            
    except Exception as e:
        if FLASK_DEBUG:
            print(f"❌ Error in API request: {url} - Error: {e}")
        return None

def load_all_anime():
    """Load semua anime dari API dan simpan di cache - MAX 30 pages"""
    global anime_cache, cache_loaded, cache_last_updated, cache_loading
    
    # Cegah multiple simultaneous loading
    if cache_loading:
        print("⚠️  Cache is already loading, skipping...")
        return anime_cache
    
    if cache_loaded and len(anime_cache) > 0:
        if FLASK_DEBUG:
            print(f"✅ Using existing cache: {len(anime_cache)} anime")
        return anime_cache
    
    cache_loading = True
    
    try:
        print("=" * 60)
        print("🔄 Loading anime cache (MAX 30 pages)...")
        print("=" * 60)
        
        all_anime = []
        total_pages_loaded = 0
        
        # Hanya gunakan 'latest' endpoint untuk mengurangi load
        endpoint_name = 'latest'
        print(f"\n📥 Loading from: {endpoint_name} (max {MAX_PAGES} pages)")
        
        for page in range(1, MAX_PAGES + 1):
            try:
                url = f"{API_BASE}/anime/{endpoint_name}?page={page}"
                
                if FLASK_DEBUG:
                    print(f"   📄 Page {page:2d}: ", end="")
                
                response = safe_api_request(url)
                
                if response:
                    try:
                        data = response.json()
                        if isinstance(data, list) and len(data) > 0:
                            all_anime.extend(data)
                            total_pages_loaded += 1
                            if FLASK_DEBUG:
                                print(f"✅ {len(data)} anime")
                        else:
                            if FLASK_DEBUG:
                                print(f"⚠️  No data (empty list)")
                            break  # No more data
                    except json.JSONDecodeError:
                        if FLASK_DEBUG:
                            print(f"❌ Invalid JSON")
                        break
                else:
                    if FLASK_DEBUG:
                        print(f"❌ Request failed")
                    break
                
                # Tambahkan delay kecil antara request
                time.sleep(REQUEST_DELAY)
                    
            except Exception as e:
                if FLASK_DEBUG:
                    print(f"❌ Error: {str(e)[:50]}")
                break
        
        if not all_anime:
            print("\n⚠️  No anime data loaded from API. Using minimal cache...")
            # Fallback ke cache minimal
            return load_minimal_cache_fallback()
        
        # Remove duplicates dan batasi ukuran cache
        seen_identifiers = set()
        unique_anime = []
        
        for anime in all_anime:
            if len(unique_anime) >= MAX_CACHE_SIZE:
                break  # Batasi ukuran cache
                
            url = anime.get('url', '')
            anime_id = anime.get('id', '')
            identifier = f"{url}|{anime_id}"
            
            if identifier and identifier not in seen_identifiers:
                seen_identifiers.add(identifier)
                unique_anime.append(anime)
        
        anime_cache = unique_anime
        cache_loaded = True
        cache_last_updated = datetime.now()
        
        print("\n" + "=" * 60)
        print("✅ CACHE LOADING COMPLETE")
        print("=" * 60)
        print(f"📊 Total unique anime cached: {len(anime_cache)}")
        print(f"📊 Total pages loaded: {total_pages_loaded}")
        print(f"📊 Max cache size: {MAX_CACHE_SIZE}")
        print(f"⏰ Last updated: {cache_last_updated.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60 + "\n")
        
        return anime_cache
        
    finally:
        cache_loading = False

def load_minimal_cache_fallback():
    """Load minimal cache sebagai fallback"""
    global anime_cache, cache_loaded, cache_last_updated
    
    print("🔄 Loading minimal fallback cache...")
    
    all_anime = []
    # Coba load 3 halaman pertama saja
    for page in range(1, 4):
        try:
            url = f"{API_BASE}/anime/latest?page={page}"
            response = safe_api_request(url)
            if response:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    all_anime.extend(data)
                    print(f"✅ Fallback: Loaded page {page} ({len(data)} anime)")
                    time.sleep(1)  # Delay lebih lama
        except:
            break
    
    if all_anime:
        # Remove duplicates
        seen = set()
        unique_anime = []
        for anime in all_anime:
            identifier = f"{anime.get('url', '')}|{anime.get('id', '')}"
            if identifier not in seen:
                seen.add(identifier)
                unique_anime.append(anime)
        
        anime_cache = unique_anime
    else:
        # Jika masih gagal, buat cache kosong
        anime_cache = []
    
    cache_loaded = True
    cache_last_updated = datetime.now()
    print(f"📊 Fallback cache: {len(anime_cache)} anime loaded")
    return anime_cache

def find_anime_by_slug(slug):
    """Cari anime berdasarkan slug atau ID dari cache"""
    all_anime = load_all_anime()
    
    # Normalize slug
    slug_normalized = slug.strip('/').lower()
    
    # Try 1: Exact URL match
    for anime in all_anime:
        anime_url = anime.get('url', '').strip('/').lower()
        if anime_url == slug_normalized:
            return anime
    
    # Try 2: Partial URL match
    for anime in all_anime:
        anime_url = anime.get('url', '').strip('/').lower()
        anime_title = anime.get('judul', '').lower()
        
        # Check if slug is part of URL or title
        if slug_normalized in anime_url or anime_url in slug_normalized:
            return anime
        
        # Try matching with title
        title_slug = anime_title.replace(' ', '-').replace(':', '').lower()
        if title_slug == slug_normalized or slug_normalized in title_slug:
            return anime
    
    # Try 3: Check if slug is actually an ID
    for anime in all_anime:
        anime_id = str(anime.get('id', ''))
        if anime_id == slug_normalized:
            return anime
    
    # Try 4: Fuzzy match on title
    slug_parts = slug_normalized.replace('-', ' ').split()
    for anime in all_anime:
        anime_title_lower = anime.get('judul', '').lower()
        if all(part in anime_title_lower for part in slug_parts if len(part) > 2):
            return anime
    
    return None

def get_episode_video(anime_data, episode_num):
    """Coba dapatkan video dengan berbagai cara"""
    try:
        anime_id = anime_data.get('id', '')
        anime_url = anime_data.get('url', '').rstrip('/')
        
        # Coba berbagai format chapterUrlId yang mungkin
        possible_chapter_ids = [
            f"al-{anime_id}-{episode_num}",
            f"al-{anime_id}-{str(episode_num).zfill(2)}",
            f"al-{anime_id}-{str(episode_num).zfill(3)}",
            f"{anime_url}-episode-{episode_num}",
            f"{anime_url}-ep-{episode_num}",
            f"{anime_url}/episode-{episode_num}",
            f"{anime_url}/{episode_num}",
            f"{anime_id}-{episode_num}",
        ]
        
        for chapter_id in possible_chapter_ids:
            try:
                video_url = f"{API_BASE}/anime/getvideo?chapterUrlId={quote(chapter_id)}"
                response = safe_api_request(video_url)
                if response:
                    data = response.json()
                    
                    # Check if there's error in response
                    if isinstance(data, dict) and 'error' in data:
                        continue
                    
                    # Check if data has streams
                    if isinstance(data, dict):
                        if 'data' in data and data['data'] and len(data['data']) > 0:
                            return data
                        elif 'stream' in data or 'video' in data:
                            return data
            except:
                continue
        
        return None
            
    except Exception as e:
        if FLASK_DEBUG:
            print(f"❌ Error getting episode video: {e}")
        return None

def check_next_page(endpoint, page, genre_name=None):
    """Cek apakah ada halaman berikutnya"""
    if page >= MAX_PAGES:
        return False
    
    try:
        if genre_name:
            next_url = f"{API_BASE}/anime/genre/{genre_name}?page={page + 1}"
        else:
            next_url = f"{API_BASE}/anime/{endpoint}?page={page + 1}"
        
        response = safe_api_request(next_url)
        if response:
            data = response.json()
            return isinstance(data, list) and len(data) > 0
    except:
        pass
    return False

def get_anime_data(endpoint, page, genre_name=None):
    """Get anime data dengan error handling"""
    if page > MAX_PAGES:
        page = MAX_PAGES
    
    try:
        if genre_name:
            url = f"{API_BASE}/anime/genre/{genre_name}?page={page}"
        else:
            url = f"{API_BASE}/anime/{endpoint}?page={page}"
        
        response = safe_api_request(url)
        if response:
            data = response.json()
            if isinstance(data, list):
                return data
    except:
        pass
    return []

# ================= ROUTES =================

@app.route('/')
def home():
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    if page > MAX_PAGES:
        page = MAX_PAGES
    
    try:
        data = get_anime_data('latest', page)
        
        # Cek apakah ada halaman berikutnya
        has_next_page = check_next_page('latest', page)
        has_prev_page = page > 1
        
        return render_template('home.html', 
                             data=data, 
                             current_page=page,
                             has_next_page=has_next_page,
                             has_prev_page=has_prev_page,
                             max_pages=MAX_PAGES,
                             endpoint_name='Latest Anime')
    except Exception as e:
        if FLASK_DEBUG:
            print(f"Error in home route: {e}")
        return render_template('home.html', 
                             data=[], 
                             current_page=page,
                             max_pages=MAX_PAGES,
                             error="Failed to load data")

@app.route('/ongoing')
def ongoing():
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    if page > MAX_PAGES:
        page = MAX_PAGES
    
    try:
        # Coba ongoing, jika gagal fallback ke latest
        data = get_anime_data('ongoing', page)
        if not data:
            data = get_anime_data('latest', page)
        
        has_next_page = check_next_page('ongoing', page)
        has_prev_page = page > 1
        
        return render_template('ongoing.html', 
                             data=data, 
                             current_page=page,
                             has_next_page=has_next_page,
                             has_prev_page=has_prev_page,
                             max_pages=MAX_PAGES,
                             endpoint_name='Ongoing Anime')
    except Exception as e:
        if FLASK_DEBUG:
            print(f"Error in ongoing route: {e}")
        return render_template('ongoing.html', 
                             data=[], 
                             current_page=page,
                             max_pages=MAX_PAGES,
                             error="Failed to load data")

@app.route('/completed')
def completed():
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    if page > MAX_PAGES:
        page = MAX_PAGES
    
    try:
        # Coba completed, jika gagal fallback ke latest
        data = get_anime_data('completed', page)
        if not data:
            data = get_anime_data('latest', page)
        
        has_next_page = check_next_page('completed', page)
        has_prev_page = page > 1
        
        return render_template('completed.html', 
                             data=data, 
                             current_page=page,
                             has_next_page=has_next_page,
                             has_prev_page=has_prev_page,
                             max_pages=MAX_PAGES,
                             endpoint_name='Completed Anime')
    except Exception as e:
        if FLASK_DEBUG:
            print(f"Error in completed route: {e}")
        return render_template('completed.html', 
                             data=[], 
                             current_page=page,
                             max_pages=MAX_PAGES,
                             error="Failed to load data")

@app.route('/movie')
def movie():
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    if page > MAX_PAGES:
        page = MAX_PAGES
    
    try:
        # Coba movie, jika gagal fallback ke latest
        data = get_anime_data('movie', page)
        if not data:
            data = get_anime_data('latest', page)
        
        has_next_page = check_next_page('movie', page)
        has_prev_page = page > 1
        
        return render_template('movie.html', 
                             data=data, 
                             current_page=page,
                             has_next_page=has_next_page,
                             has_prev_page=has_prev_page,
                             max_pages=MAX_PAGES,
                             endpoint_name='Movie Anime',
                             error=None)
    except Exception as e:
        if FLASK_DEBUG:
            print(f"Error in movie route: {e}")
        return render_template('movie.html', 
                             data=[], 
                             current_page=page, 
                             error="Failed to load data",
                             max_pages=MAX_PAGES)

@app.route('/search')
def search():
    """Server-side search untuk handle API response yang nested"""
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    
    if page < 1:
        page = 1
    if page > MAX_PAGES:
        page = MAX_PAGES
    
    if not query:
        return render_template('search.html', 
                             query='', 
                             data=[], 
                             error=None,
                             current_page=page,
                             max_pages=MAX_PAGES)
    
    try:
        # Call API search
        url = f"{API_BASE}/anime/search?query={quote(query)}"
        
        response = safe_api_request(url)
        if not response:
            return render_template('search.html', 
                                 query=query, 
                                 data=[], 
                                 error="Search API not available",
                                 current_page=page,
                                 max_pages=MAX_PAGES)
        
        # Parse JSON response
        try:
            data = response.json()
        except:
            return render_template('search.html', 
                                 query=query, 
                                 data=[], 
                                 error="Invalid response from API",
                                 current_page=page,
                                 max_pages=MAX_PAGES)
        
        # Parse nested structure
        results = []
        
        if isinstance(data, dict) and 'data' in data:
            inner_data = data['data']
            
            if isinstance(inner_data, list) and len(inner_data) > 0:
                first_element = inner_data[0]
                
                if isinstance(first_element, dict) and 'result' in first_element:
                    results = first_element['result'] if isinstance(first_element['result'], list) else []
                else:
                    results = inner_data
            elif isinstance(inner_data, dict) and 'result' in inner_data:
                results = inner_data['result'] if isinstance(inner_data['result'], list) else []
        
        elif isinstance(data, list):
            results = data
        elif isinstance(data, dict) and 'result' in data:
            results = data['result'] if isinstance(data['result'], list) else []
        elif isinstance(data, dict) and 'results' in data:
            results = data['results'] if isinstance(data['results'], list) else []
        
        # Paginate results manually
        items_per_page = 20
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        paginated_results = results[start_idx:end_idx]
        
        has_next_page = len(results) > end_idx
        has_prev_page = page > 1
        
        return render_template('search.html', 
                             query=query, 
                             data=paginated_results, 
                             error=None,
                             current_page=page,
                             has_next_page=has_next_page,
                             has_prev_page=has_prev_page,
                             max_pages=MAX_PAGES,
                             total_results=len(results))
        
    except Exception as e:
        if FLASK_DEBUG:
            print(f"Error in search route: {e}")
        return render_template('search.html', 
                             query=query, 
                             data=[], 
                             error=f"Search error: {str(e)}",
                             current_page=page,
                             max_pages=MAX_PAGES)

@app.route('/anime/<path:slug>')
def anime_detail(slug):
    """Detail anime page"""
    try:
        if FLASK_DEBUG:
            print(f"\n📺 Accessing anime: {slug}")
        
        # Cari di cache terlebih dahulu
        anime_data = find_anime_by_slug(slug)
        
        if anime_data:
            # Generate episode list jika tidak ada
            if 'episode_list' not in anime_data or not anime_data['episode_list']:
                total_eps = anime_data.get('total_episode', 12)
                if isinstance(total_eps, int) and total_eps > 0:
                    anime_data['episode_list'] = [
                        {
                            'episode': i,
                            'url': f"{slug.rstrip('/')}/episode-{i}/",
                            'title': f"Episode {i}",
                            'date': ''
                        }
                        for i in range(1, min(total_eps + 1, 100))
                    ]
            
            return render_template('detail.html', anime=anime_data)
        
        # Anime tidak ditemukan
        return render_template('error.html', 
                             error_message=f"Anime '{slug}' tidak ditemukan",
                             suggestion="Coba cari anime di halaman search")
        
    except Exception as e:
        if FLASK_DEBUG:
            print(f"Error in anime_detail route: {e}")
        return render_template('error.html', 
                             error_message="Terjadi kesalahan saat memuat anime",
                             suggestion="Coba lagi nanti atau gunakan fitur search")

@app.route('/watch/<path:slug>')
def watch(slug):
    """Watch episode page"""
    try:
        # Parse anime slug dan episode number
        parts = slug.rstrip('/').split('/')
        
        episode_num = ''
        anime_slug = ''
        
        if len(parts) >= 2:
            anime_slug = '/'.join(parts[:-1]) + '/'
            episode_part = parts[-1]
            if 'episode-' in episode_part:
                episode_num = episode_part.replace('episode-', '')
            elif 'ep-' in episode_part:
                episode_num = episode_part.replace('ep-', '')
        else:
            if 'episode-' in slug:
                split_ep = slug.rsplit('episode-', 1)
                anime_slug = split_ep[0].rstrip('-') + '/'
                episode_num = split_ep[1].rstrip('/')
            elif 'ep-' in slug:
                split_ep = slug.rsplit('ep-', 1)
                anime_slug = split_ep[0].rstrip('-') + '/'
                episode_num = split_ep[1].rstrip('/')
            else:
                anime_slug = slug
        
        # Cari anime data dari cache
        anime_data = find_anime_by_slug(anime_slug)
        
        if not anime_data:
            return render_template('error.html',
                                 error_message=f"Anime tidak ditemukan: {anime_slug}",
                                 suggestion="Kembali ke halaman utama dan cari anime")
        
        anime_title = anime_data.get('judul', 'Unknown')
        
        # Get video data dari API
        video_data = get_episode_video(anime_data, episode_num)
        
        # Buat episode data
        episode_data = {
            'title': f'{anime_title} - Episode {episode_num}',
            'anime_url': anime_slug,
            'anime_title': anime_title,
            'episode': episode_num,
            'video_data': video_data,
            'prev_episode': int(episode_num) - 1 if episode_num and episode_num.isdigit() and int(episode_num) > 1 else None,
            'next_episode': int(episode_num) + 1 if episode_num and episode_num.isdigit() else None,
        }
        
        return render_template('watch.html', episode=episode_data)
        
    except Exception as e:
        if FLASK_DEBUG:
            print(f"Error in watch route: {e}")
        return render_template('error.html',
                             error_message="Terjadi kesalahan saat memuat video",
                             suggestion="Coba lagi nanti atau pilih episode lain")

@app.route('/genre/<genre_name>')
def genre(genre_name):
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    if page > MAX_PAGES:
        page = MAX_PAGES
    
    try:
        data = get_anime_data(None, page, genre_name)
        
        # Jika genre tidak ada data, fallback ke latest
        if not data:
            data = get_anime_data('latest', page)
            genre_name = f"Latest (Genre '{genre_name}' not found)"
        
        has_next_page = check_next_page(None, page, genre_name)
        has_prev_page = page > 1
        
        return render_template('genre.html', 
                             data=data, 
                             genre_name=genre_name, 
                             current_page=page,
                             has_next_page=has_next_page,
                             has_prev_page=has_prev_page,
                             max_pages=MAX_PAGES)
    except Exception as e:
        if FLASK_DEBUG:
            print(f"Error in genre route: {e}")
        return render_template('genre.html', 
                             data=[], 
                             genre_name=genre_name, 
                             current_page=page,
                             max_pages=MAX_PAGES,
                             error="Failed to load genre data")

@app.route('/health')
def health_check():
    """Health check endpoint untuk Railway"""
    return jsonify({
        'status': 'healthy',
        'cache_loaded': cache_loaded,
        'cache_size': len(anime_cache),
        'server_time': datetime.now().isoformat(),
        'max_pages': MAX_PAGES
    }), 200

@app.route('/cache/reload')
def reload_cache():
    """Reload anime cache"""
    global anime_cache, cache_loaded, cache_last_updated
    anime_cache = []
    cache_loaded = False
    load_all_anime()
    
    return jsonify({
        'status': 'success',
        'message': 'Cache reloaded successfully',
        'cache_size': len(anime_cache),
        'timestamp': cache_last_updated.isoformat() if cache_last_updated else None
    })

@app.route('/cache/info')
def cache_info():
    """Show cache info"""
    load_all_anime()
    
    return jsonify({
        'status': 'success',
        'cache_info': {
            'total_anime': len(anime_cache),
            'cache_loaded': cache_loaded,
            'max_pages': MAX_PAGES,
            'max_cache_size': MAX_CACHE_SIZE,
            'max_retries': MAX_RETRIES,
            'retry_delay': RETRY_DELAY,
            'request_delay': REQUEST_DELAY,
            'last_updated': cache_last_updated.isoformat() if cache_last_updated else None
        },
        'server_info': {
            'debug_mode': FLASK_DEBUG,
            'api_base': API_BASE,
            'server_time': datetime.now().isoformat()
        }
    })

@app.route('/api/test')
def api_test():
    """Test API endpoints"""
    test_results = {}
    
    endpoints = [
        ('latest', f"{API_BASE}/anime/latest?page=1"),
        ('search', f"{API_BASE}/anime/search?query=naruto"),
    ]
    
    for name, url in endpoints:
        try:
            response = safe_api_request(url)
            if response:
                test_results[name] = {
                    'status': 'available',
                    'status_code': response.status_code,
                    'url': url
                }
            else:
                test_results[name] = {
                    'status': 'unavailable',
                    'url': url
                }
        except Exception as e:
            test_results[name] = {
                'status': 'error',
                'error': str(e),
                'url': url
            }
    
    return jsonify({
        'api_test': test_results,
        'cache_info': {
            'loaded': cache_loaded,
            'size': len(anime_cache)
        },
        'server_time': datetime.now().isoformat()
    })

@app.route('/stats')
def stats():
    """Server statistics"""
    load_all_anime()
    
    return jsonify({
        'server': {
            'max_pages': MAX_PAGES,
            'max_cache_size': MAX_CACHE_SIZE,
            'cache_size': len(anime_cache),
            'cache_loaded': cache_loaded,
            'api_base': API_BASE,
            'debug_mode': FLASK_DEBUG,
            'server_time': datetime.now().isoformat()
        },
        'endpoints': [
            {'path': '/', 'description': 'Home page'},
            {'path': '/ongoing', 'description': 'Ongoing anime'},
            {'path': '/completed', 'description': 'Completed anime'},
            {'path': '/movie', 'description': 'Movie anime'},
            {'path': '/search?q=query', 'description': 'Search anime'},
            {'path': '/anime/slug', 'description': 'Anime detail'},
            {'path': '/watch/slug/episode-N', 'description': 'Watch episode'},
            {'path': '/genre/genre-name', 'description': 'Genre anime'},
            {'path': '/health', 'description': 'Health check'},
            {'path': '/cache/info', 'description': 'Cache information'},
            {'path': '/api/test', 'description': 'API test'}
        ]
    })

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html',
                         error_message="Halaman tidak ditemukan",
                         suggestion="Gunakan menu navigasi untuk kembali ke halaman yang tersedia"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html',
                         error_message="Terjadi kesalahan internal server",
                         suggestion="Coba refresh halaman atau kembali nanti"), 500

# ================= MAIN =================

if __name__ == '__main__':
    # Gunakan PORT dari environment variable (Railway menyediakan)
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 60)
    print("🚀 ANIME STREAMING SERVER - Railway Optimized")
    print("=" * 60)
    print(f"📊 Max Pages: {MAX_PAGES}")
    print(f"📊 Max Cache Size: {MAX_CACHE_SIZE}")
    print(f"🌐 API Base: {API_BASE}")
    print(f"⚙️  Max Retries: {MAX_RETRIES}")
    print(f"⏱️  Retry Delay: {RETRY_DELAY}s")
    print(f"⏳ Request Delay: {REQUEST_DELAY}s")
    print(f"🐛 Debug Mode: {FLASK_DEBUG}")
    print(f"🌐 Server Port: {port}")
    print("=" * 60)
    
    # Load cache di background thread
    import threading
    def load_cache_background():
        try:
            load_all_anime()
        except Exception as e:
            print(f"❌ Error loading cache: {e}")
    
    cache_thread = threading.Thread(target=load_cache_background, daemon=True)
    cache_thread.start()
    
    print("🔧 Cache loading started in background thread...")
    print("✅ Server is starting...")
    print("=" * 60)
    
    # Run server
    app.run(
        debug=FLASK_DEBUG, 
        host='0.0.0.0', 
        port=port, 
        threaded=True,
        use_reloader=False  # Penting untuk production!
    )