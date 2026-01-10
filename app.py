# app.py - COMPLETE Vercel-Compatible Anime Streaming App
import os
from flask import Flask, render_template, request, jsonify
import requests
from urllib.parse import quote
import json
import time
from datetime import datetime
from functools import lru_cache
import hashlib

# Inisialisasi Flask app
app = Flask(__name__)

# Configuration dari environment variables
API_BASE = os.environ.get('API_BASE', 'https://api.sansekai.my.id/api')
MAX_PAGES = int(os.environ.get('MAX_PAGES', 100))
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', 3))
RETRY_DELAY = float(os.environ.get('RETRY_DELAY', 2.0))
REQUEST_DELAY = float(os.environ.get('REQUEST_DELAY', 0.3))
CACHE_TTL = int(os.environ.get('CACHE_TTL', 300))

# Cache in-memory
memory_cache = {}
cache_timestamps = {}

# Helper function untuk logging
def log_info(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] ℹ️  {message}")

def log_warning(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] ⚠️  {message}")

def log_error(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] ❌ {message}")

def log_success(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] ✅ {message}")

def safe_api_request(url, retry_count=0):
    """Fungsi aman untuk request API dengan retry mechanism"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 429:
            if retry_count < MAX_RETRIES:
                wait_time = RETRY_DELAY * (retry_count + 1)
                log_warning(f"Rate limited (429). Waiting {wait_time}s...")
                time.sleep(wait_time)
                return safe_api_request(url, retry_count + 1)
            return None
        
        if response.status_code != 200:
            return None
        
        return response
        
    except requests.exceptions.Timeout:
        if retry_count < MAX_RETRIES:
            wait_time = RETRY_DELAY * (retry_count + 1)
            time.sleep(wait_time)
            return safe_api_request(url, retry_count + 1)
        return None
            
    except Exception:
        return None

def get_cached_or_fetch(cache_key, fetch_func, ttl=CACHE_TTL):
    """Dapatkan data dari cache atau fetch baru"""
    current_time = time.time()
    
    if cache_key in memory_cache:
        cache_time = cache_timestamps.get(cache_key, 0)
        if current_time - cache_time < ttl:
            return memory_cache[cache_key]
    
    data = fetch_func()
    
    if data is not None:
        memory_cache[cache_key] = data
        cache_timestamps[cache_key] = current_time
    
    return data

@lru_cache(maxsize=100)
def fetch_all_anime():
    """Fetch semua anime dari API - SEMUA ENDPOINT dengan 100 halaman!"""
    log_info("Fetching anime data from ALL endpoints...")
    
    all_anime = []
    
    # LOAD DARI SEMUA 4 ENDPOINT!
    endpoints_to_try = ['latest', 'ongoing', 'completed', 'movie']
    
    for endpoint_name in endpoints_to_try:
        log_info(f"Loading from endpoint: {endpoint_name}")
        pages_loaded = 0
        consecutive_empty = 0
        
        # Load sampai 100 halaman per endpoint
        for page in range(1, min(MAX_PAGES + 1, 101)):
            try:
                url = f"{API_BASE}/anime/{endpoint_name}?page={page}"
                response = safe_api_request(url)
                
                if response:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        all_anime.extend(data)
                        pages_loaded += 1
                        consecutive_empty = 0
                    else:
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            break
                else:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                
                time.sleep(REQUEST_DELAY)
                    
            except Exception as e:
                log_error(f"Error page {page} from {endpoint_name}: {str(e)}")
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
        
        log_success(f"Loaded {pages_loaded} pages from {endpoint_name}")
        time.sleep(1)
    
    # Remove duplicates
    seen_identifiers = set()
    unique_anime = []
    
    for anime in all_anime:
        url = anime.get('url', '')
        anime_id = anime.get('id', '')
        identifier = f"{url}|{anime_id}"
        
        if identifier and identifier not in seen_identifiers and identifier != '|':
            seen_identifiers.add(identifier)
            unique_anime.append(anime)
    
    log_success(f"Total: {len(all_anime)}, Unique: {len(unique_anime)}")
    return unique_anime

def find_anime_by_slug(slug):
    """Cari anime di cache ATAU via Search API (FALLBACK!)"""
    try:
        all_anime = fetch_all_anime()
        slug_normalized = slug.strip('/').lower()
        
        # Try 1: Exact URL match
        for anime in all_anime:
            anime_url = anime.get('url', '').strip('/').lower()
            if anime_url == slug_normalized:
                return anime
        
        # Try 2: Partial URL match
        for anime in all_anime:
            anime_url = anime.get('url', '').strip('/').lower()
            if slug_normalized in anime_url or anime_url in slug_normalized:
                return anime
        
        # Try 3: ID match
        for anime in all_anime:
            if str(anime.get('id', '')) == slug_normalized:
                return anime
        
        # Try 4: SEARCH API FALLBACK! (KUNCI SOLUSI!)
        log_warning(f"Not in cache, trying Search API for: {slug}")
        
        search_query = slug.replace('-', ' ').strip()
        search_url = f"{API_BASE}/anime/search?query={quote(search_query)}"
        
        response = safe_api_request(search_url)
        if response:
            data = response.json()
            
            # Parse search result
            results = []
            if isinstance(data, dict) and 'data' in data:
                inner = data['data']
                if isinstance(inner, list) and len(inner) > 0:
                    first = inner[0]
                    if isinstance(first, dict) and 'result' in first:
                        results = first['result'] if isinstance(first['result'], list) else []
            
            # Find matching anime
            for result in results:
                result_url = result.get('url', '').strip('/').lower()
                result_id = str(result.get('id', ''))
                
                if (result_url == slug_normalized or 
                    slug_normalized in result_url or 
                    result_url in slug_normalized or
                    result_id == slug_normalized):
                    log_success(f"Found via Search API: {result.get('judul')}")
                    return result
        
        return None
        
    except Exception as e:
        log_error(f"Error finding anime: {str(e)}")
        return None

def get_episode_video(anime_data, episode_num):
    """Coba dapatkan video dengan berbagai cara"""
    try:
        anime_id = anime_data.get('id', '')
        anime_url = anime_data.get('url', '').rstrip('/')
        
        possible_chapter_ids = [
            f"al-{anime_id}-{episode_num}",
            f"al-{anime_id}-{str(episode_num).zfill(2)}",
            f"al-{anime_id}-{str(episode_num).zfill(3)}",
            f"{anime_url}-episode-{episode_num}",
            f"{anime_url}-ep-{episode_num}",
        ]
        
        for chapter_id in possible_chapter_ids:
            try:
                video_url = f"{API_BASE}/anime/getvideo?chapterUrlId={quote(chapter_id)}"
                response = safe_api_request(video_url)
                if response:
                    data = response.json()
                    
                    if isinstance(data, dict):
                        if 'error' in data:
                            continue
                        if 'data' in data and data['data']:
                            return data
                        elif 'stream' in data:
                            return data
            except:
                continue
        
        return None
            
    except Exception as e:
        log_error(f"Error getting video: {str(e)}")
        return None

def check_next_page(endpoint, page, genre_name=None):
    """Cek apakah ada halaman berikutnya"""
    try:
        if genre_name:
            url = f"{API_BASE}/anime/genre/{genre_name}?page={page + 1}"
        else:
            url = f"{API_BASE}/anime/{endpoint}?page={page + 1}"
        
        response = safe_api_request(url)
        if response:
            data = response.json()
            return isinstance(data, list) and len(data) > 0
    except:
        pass
    return False

def get_anime_data(endpoint, page, genre_name=None):
    """Get anime data dengan error handling dan caching"""
    cache_key = f"anime_data_{endpoint}_{genre_name}_{page}"
    
    def fetch_data():
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
        except Exception as e:
            log_error(f"Error fetching anime data: {str(e)}")
        return []
    
    return get_cached_or_fetch(cache_key, fetch_data)

# ==================== ROUTES ====================

@app.route('/')
def home():
    page = request.args.get('page', 1, type=int)
    page = max(1, min(page, MAX_PAGES))
    
    try:
        data = get_anime_data('latest', page)
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
        log_error(f"Home error: {str(e)}")
        return render_template('home.html', 
                             data=[], 
                             current_page=page,
                             max_pages=MAX_PAGES)

@app.route('/ongoing')
def ongoing():
    page = request.args.get('page', 1, type=int)
    page = max(1, min(page, MAX_PAGES))
    
    try:
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
        log_error(f"Ongoing error: {str(e)}")
        return render_template('ongoing.html', 
                             data=[], 
                             current_page=page,
                             max_pages=MAX_PAGES)

@app.route('/completed')
def completed():
    page = request.args.get('page', 1, type=int)
    page = max(1, min(page, MAX_PAGES))
    
    try:
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
        log_error(f"Completed error: {str(e)}")
        return render_template('completed.html', 
                             data=[], 
                             current_page=page,
                             max_pages=MAX_PAGES)

@app.route('/movie')
def movie():
    page = request.args.get('page', 1, type=int)
    page = max(1, min(page, MAX_PAGES))
    
    try:
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
                             endpoint_name='Movie Anime')
    except Exception as e:
        log_error(f"Movie error: {str(e)}")
        return render_template('movie.html', 
                             data=[], 
                             current_page=page,
                             max_pages=MAX_PAGES)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    page = max(1, min(page, MAX_PAGES))
    
    if not query:
        return render_template('search.html', 
                             query='', 
                             data=[],
                             current_page=page,
                             max_pages=MAX_PAGES)
    
    try:
        cache_key = f"search_{hashlib.md5(query.encode()).hexdigest()}_{page}"
        
        def fetch_search_results():
            url = f"{API_BASE}/anime/search?query={quote(query)}"
            response = safe_api_request(url)
            
            if not response:
                return []
            
            data = response.json()
            results = []
            
            if isinstance(data, dict) and 'data' in data:
                inner_data = data['data']
                
                if isinstance(inner_data, list) and len(inner_data) > 0:
                    first_element = inner_data[0]
                    
                    if isinstance(first_element, dict) and 'result' in first_element:
                        results = first_element['result'] if isinstance(first_element['result'], list) else []
                    else:
                        results = inner_data
            return results
        
        results = get_cached_or_fetch(cache_key, fetch_search_results, ttl=60)
        
        # Manual pagination
        items_per_page = 20
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        paginated_results = results[start_idx:end_idx] if results else []
        
        has_next_page = len(results) > end_idx if results else False
        has_prev_page = page > 1
        
        return render_template('search.html', 
                             query=query, 
                             data=paginated_results,
                             current_page=page,
                             has_next_page=has_next_page,
                             has_prev_page=has_prev_page,
                             max_pages=MAX_PAGES,
                             total_results=len(results) if results else 0)
        
    except Exception as e:
        log_error(f"Search error: {str(e)}")
        return render_template('search.html', 
                             query=query, 
                             data=[],
                             current_page=page,
                             max_pages=MAX_PAGES)

@app.route('/anime/<path:slug>')
def anime_detail(slug):
    try:
        anime_data = find_anime_by_slug(slug)
        
        if anime_data:
            # Generate episode list
            total_eps = anime_data.get('total_episode', 12)
            if isinstance(total_eps, str) and total_eps.isdigit():
                total_eps = int(total_eps)
            elif not isinstance(total_eps, int):
                total_eps = 12
            
            if total_eps > 0:
                anime_data['episode_list'] = [
                    {
                        'episode': i,
                        'url': f"/watch/{slug.rstrip('/')}/episode-{i}/",
                        'title': f"Episode {i}",
                        'date': ''
                    }
                    for i in range(1, min(total_eps + 1, 500))
                ]
            
            return render_template('detail.html', anime=anime_data)
        
        return render_template('error.html', 
                             error_message=f"Anime '{slug}' tidak ditemukan",
                             suggestion="Coba cari anime di halaman search"), 404
        
    except Exception as e:
        log_error(f"Detail error: {str(e)}")
        return render_template('error.html', 
                             error_message="Terjadi kesalahan saat memuat anime",
                             suggestion="Coba lagi nanti atau gunakan fitur search"), 500

@app.route('/watch/<path:slug>')
def watch(slug):
    try:
        # Parse episode
        if 'episode-' in slug:
            parts = slug.split('episode-')
            anime_slug = parts[0].rstrip('-/')
            episode_num = parts[1].rstrip('/')
        elif 'ep-' in slug:
            parts = slug.split('ep-')
            anime_slug = parts[0].rstrip('-/')
            episode_num = parts[1].rstrip('/')
        else:
            return render_template('error.html',
                                 error_message="Format URL tidak valid",
                                 suggestion="Gunakan format: /watch/anime-slug/episode-N"), 400
        
        anime_data = find_anime_by_slug(anime_slug)
        
        if not anime_data:
            return render_template('error.html',
                                 error_message=f"Anime tidak ditemukan: {anime_slug}",
                                 suggestion="Kembali ke halaman utama"), 404
        
        # Get video with cache
        cache_key = f"video_{anime_slug}_{episode_num}"
        
        def fetch_video():
            return get_episode_video(anime_data, episode_num)
        
        video_data = get_cached_or_fetch(cache_key, fetch_video, ttl=1800)
        
        episode_data = {
            'title': f"{anime_data.get('judul', 'Unknown')} - Episode {episode_num}",
            'anime_url': f"/anime/{anime_slug}",
            'anime_title': anime_data.get('judul', 'Unknown'),
            'episode': episode_num,
            'video_data': video_data,
            'prev_episode': int(episode_num) - 1 if episode_num.isdigit() and int(episode_num) > 1 else None,
            'next_episode': int(episode_num) + 1 if episode_num.isdigit() else None,
        }
        
        return render_template('watch.html', episode=episode_data)
        
    except Exception as e:
        log_error(f"Watch error: {str(e)}")
        return render_template('error.html',
                             error_message="Terjadi kesalahan saat memuat video",
                             suggestion="Coba lagi nanti atau pilih episode lain"), 500

@app.route('/genre/<genre_name>')
def genre(genre_name):
    page = request.args.get('page', 1, type=int)
    page = max(1, min(page, MAX_PAGES))
    
    try:
        data = get_anime_data(None, page, genre_name)
        
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
        log_error(f"Genre error: {str(e)}")
        return render_template('genre.html', 
                             data=[], 
                             genre_name=genre_name, 
                             current_page=page,
                             max_pages=MAX_PAGES)

@app.route('/health')
def health_check():
    """Health check endpoint untuk Vercel"""
    return jsonify({
        'status': 'healthy',
        'service': 'anime-streaming-api',
        'timestamp': datetime.now().isoformat(),
        'cache_size': len(memory_cache),
        'max_pages_supported': MAX_PAGES,
        'environment': 'vercel'
    })

@app.route('/api/status')
def api_status():
    """API status endpoint"""
    return jsonify({
        'status': 'online',
        'version': '2.0.0',
        'api_base': API_BASE,
        'cache_info': {
            'memory_cache_entries': len(memory_cache),
            'cache_ttl': CACHE_TTL
        },
        'features': [
            'Search API fallback',
            '100 pages loading',
            '4 endpoints support',
            'Smart caching'
        ],
        'server_time': datetime.now().isoformat()
    })

@app.route('/api/search')
def api_search():
    """API search endpoint"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'Query parameter required'}), 400
    
    try:
        url = f"{API_BASE}/anime/search?query={quote(query)}"
        response = safe_api_request(url)
        
        if not response:
            return jsonify({'error': 'Failed to fetch data', 'results': []})
        
        data = response.json()
        results = []
        
        if isinstance(data, dict) and 'data' in data:
            inner_data = data['data']
            
            if isinstance(inner_data, list) and len(inner_data) > 0:
                first_element = inner_data[0]
                
                if isinstance(first_element, dict) and 'result' in first_element:
                    results = first_element['result'] if isinstance(first_element['result'], list) else []
                else:
                    results = inner_data
        
        return jsonify({
            'query': query,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        return jsonify({'error': str(e), 'results': []}), 500

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

# Handler untuk Vercel serverless
app = app

# Main execution
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 70)
    print("🚀 ANIME STREAMING SERVER - COMPLETE VERSION")
    print("=" * 70)
    print(f"📊 Max Pages: {MAX_PAGES}")
    print(f"📦 Cache TTL: {CACHE_TTL} seconds")
    print(f"🌐 API Base: {API_BASE}")
    print(f"🔧 Debug Mode: {app.debug}")
    print(f"📡 Port: {port}")
    print("=" * 70)
    print("🔥 Features:")
    print("   ✅ 100 pages from 4 endpoints (~8000 anime)")
    print("   ✅ Search API fallback for missing anime")
    print("   ✅ Smart caching system")
    print("   ✅ Vercel serverless compatible")
    print("=" * 70)
    print("📋 Routes:")
    print("   Home:        http://localhost:5000")
    print("   Search:      http://localhost:5000/search?q=query")
    print("   Health:      http://localhost:5000/health")
    print("   API Status:  http://localhost:5000/api/status")
    print("=" * 70)
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.environ.get('DEBUG', 'False').lower() == 'true',
        threaded=True
    )
