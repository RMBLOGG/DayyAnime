# app.py - Vercel-Compatible Anime Streaming App
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
CACHE_TTL = int(os.environ.get('CACHE_TTL', 300))  # Cache waktu hidup di Vercel (detik)

# Cache in-memory (sementara untuk Vercel)
memory_cache = {}
cache_timestamps = {}

# Helper function untuk logging
def log_info(message):
    """Log informasi dengan timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] ℹ️  {message}")

def log_warning(message):
    """Log warning dengan timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] ⚠️  {message}")

def log_error(message):
    """Log error dengan timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] ❌ {message}")

def log_success(message):
    """Log success dengan timestamp"""
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
        
        # Handle rate limiting (429)
        if response.status_code == 429:
            if retry_count < MAX_RETRIES:
                wait_time = RETRY_DELAY * (retry_count + 1)
                log_warning(f"Rate limited (429). Waiting {wait_time}s...")
                time.sleep(wait_time)
                return safe_api_request(url, retry_count + 1)
            return None
        
        # Handle other status codes
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
    
    # Cek cache
    if cache_key in memory_cache:
        cache_time = cache_timestamps.get(cache_key, 0)
        if current_time - cache_time < ttl:
            return memory_cache[cache_key]
    
    # Fetch baru
    data = fetch_func()
    
    # Simpan ke cache
    if data is not None:
        memory_cache[cache_key] = data
        cache_timestamps[cache_key] = current_time
    
    return data

@lru_cache(maxsize=100)
def fetch_all_anime():
    """Fetch semua anime dari API (dengan LRU cache)"""
    log_info("Fetching anime data from API...")
    
    all_anime = []
    endpoints_to_try = ['latest']
    
    for endpoint_name in endpoints_to_try:
        for page in range(1, 6):  # Hanya fetch 5 halaman untuk Vercel
            try:
                url = f"{API_BASE}/anime/{endpoint_name}?page={page}"
                response = safe_api_request(url)
                
                if response:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        all_anime.extend(data)
                    else:
                        break
                
                time.sleep(REQUEST_DELAY)
                    
            except Exception as e:
                log_error(f"Error fetching page {page}: {str(e)}")
                break
    
    # Remove duplicates
    seen_identifiers = set()
    unique_anime = []
    
    for anime in all_anime:
        url = anime.get('url', '')
        anime_id = anime.get('id', '')
        identifier = f"{url}|{anime_id}"
        
        if identifier and identifier not in seen_identifiers:
            seen_identifiers.add(identifier)
            unique_anime.append(anime)
    
    log_success(f"Fetched {len(unique_anime)} anime")
    return unique_anime

def find_anime_by_slug(slug):
    """Cari anime berdasarkan slug atau ID"""
    try:
        all_anime = fetch_all_anime()
        
        if not all_anime:
            return None
        
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
        
        # Try 3: Match by title/slug parts
        for anime in all_anime:
            anime_title = anime.get('judul', '').lower()
            if slug_normalized in anime_title or any(part in slug_normalized for part in anime_title.split()):
                return anime
        
        return None
        
    except Exception as e:
        log_error(f"Error finding anime: {str(e)}")
        return None

def get_episode_video(anime_data, episode_num):
    """Coba dapatkan video dengan berbagai cara"""
    try:
        anime_id = anime_data.get('id', '')
        anime_url = anime_data.get('url', '').rstrip('/')
        
        # Coba berbagai format chapterUrlId
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
                    for i in range(1, min(total_eps + 1, 100))
                ]
            
            return render_template('detail.html', anime=anime_data)
        
        return render_template('error.html', 
                             error_message=f"Anime '{slug}' tidak ditemukan",
                             suggestion="Coba cari anime di halaman search")
        
    except Exception as e:
        log_error(f"Detail error: {str(e)}")
        return render_template('error.html', 
                             error_message="Terjadi kesalahan saat memuat anime",
                             suggestion="Coba lagi nanti atau gunakan fitur search")

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
                                 suggestion="Gunakan format: /watch/anime-slug/episode-N")
        
        anime_data = find_anime_by_slug(anime_slug)
        
        if not anime_data:
            return render_template('error.html',
                                 error_message=f"Anime tidak ditemukan: {anime_slug}",
                                 suggestion="Kembali ke halaman utama")
        
        # Get video with cache
        cache_key = f"video_{anime_slug}_{episode_num}"
        
        def fetch_video():
            return get_episode_video(anime_data, episode_num)
        
        video_data = get_cached_or_fetch(cache_key, fetch_video, ttl=1800)  # Cache 30 menit untuk video
        
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
                             suggestion="Coba lagi nanti atau pilih episode lain")

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
        'version': '1.0.0',
        'api_base': API_BASE,
        'cache_info': {
            'memory_cache_entries': len(memory_cache),
            'cache_ttl': CACHE_TTL
        },
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

# ==================== VERCEL HANDLER ====================

# Handler untuk Vercel serverless
app = app

# ==================== MAIN EXECUTION ====================

if __name__ == '__main__':
    # Dapatkan port dari environment variable
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 60)
    print("🚀 ANIME STREAMING SERVER - VERCEL COMPATIBLE")
    print("=" * 60)
    print(f"📊 Max Pages: {MAX_PAGES}")
    print(f"📦 Cache TTL: {CACHE_TTL} seconds")
    print(f"🌐 API Base: {API_BASE}")
    print(f"🔧 Debug Mode: {app.debug}")
    print(f"📡 Port: {port}")
    print("=" * 60)
    print("📋 Available Routes:")
    print("   Home:        http://localhost:5000")
    print("   Ongoing:     http://localhost:5000/ongoing")
    print("   Completed:   http://localhost:5000/completed")
    print("   Movie:       http://localhost:5000/movie")
    print("   Search:      http://localhost:5000/search?q=query")
    print("   Health:      http://localhost:5000/health")
    print("   API Status:  http://localhost:5000/api/status")
    print("   API Search:  http://localhost:5000/api/search?q=query")
    print("=" * 60)
    
    # Run server
    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.environ.get('DEBUG', 'False').lower() == 'true',
        threaded=True
    )