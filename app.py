
# app.py - Production Ready for Railway dengan 100 Page Support
import os
from flask import Flask, render_template, request, jsonify
import requests
from urllib.parse import quote
import json
import time
from datetime import datetime
import threading

# Inisialisasi Flask app
app = Flask(__name__)

# Configuration dari environment variables
API_BASE = os.environ.get('API_BASE', 'https://api.sansekai.my.id/api')
MAX_PAGES = int(os.environ.get('MAX_PAGES', 100))  # 100 PAGES untuk semua endpoint
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', 3))
RETRY_DELAY = float(os.environ.get('RETRY_DELAY', 2.0))
REQUEST_DELAY = float(os.environ.get('REQUEST_DELAY', 1.0))  # ⭐ DITINGKATKAN dari 0.3 ke 1.0 DETIK
CACHE_MAX_PAGES = int(os.environ.get('CACHE_MAX_PAGES', 50))  # Cache 50 pages untuk performance

# Cache untuk menyimpan semua anime
anime_cache = []
cache_loaded = False
cache_loading = False

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

def load_all_anime():
    """Load semua anime dari API dan simpan di cache"""
    global anime_cache, cache_loaded, cache_loading
    
    if cache_loading:
        return anime_cache
    
    if cache_loaded and len(anime_cache) > 0:
        return anime_cache
    
    cache_loading = True
    log_info("Loading anime cache...")
    
    all_anime = []
    
    # Hanya load dari endpoint yang tersedia
    endpoints_to_try = ['latest']
    
    for endpoint_name in endpoints_to_try:
        for page in range(1, CACHE_MAX_PAGES + 1):
            try:
                url = f"{API_BASE}/anime/{endpoint_name}?page={page}"
                response = safe_api_request(url)
                
                if response:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        all_anime.extend(data)
                    else:
                        break
                
                # ⭐ DELAY ANTAR REQUEST: 1.0 DETIK (mengurangi rate limiting)
                time.sleep(REQUEST_DELAY)
                    
            except Exception:
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
    
    anime_cache = unique_anime
    cache_loaded = True
    cache_loading = False
    
    log_success(f"Cache loaded: {len(anime_cache)} anime")
    return anime_cache

def find_anime_by_slug(slug):
    """Cari anime berdasarkan slug atau ID dari cache"""
    all_anime = load_all_anime()
    
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
            
    except Exception:
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
    """Get anime data dengan error handling"""
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
        url = f"{API_BASE}/anime/search?query={quote(query)}"
        response = safe_api_request(url)
        
        if not response:
            return render_template('search.html', 
                                 query=query, 
                                 data=[],
                                 current_page=page,
                                 max_pages=MAX_PAGES)
        
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
        
        # Manual pagination
        items_per_page = 20
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        paginated_results = results[start_idx:end_idx]
        
        has_next_page = len(results) > end_idx
        has_prev_page = page > 1
        
        return render_template('search.html', 
                             query=query, 
                             data=paginated_results,
                             current_page=page,
                             has_next_page=has_next_page,
                             has_prev_page=has_prev_page,
                             max_pages=MAX_PAGES,
                             total_results=len(results))
        
    except Exception:
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
        
        return render_template('error.html', 
                             error_message=f"Anime '{slug}' tidak ditemukan",
                             suggestion="Coba cari anime di halaman search")
        
    except Exception:
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
        
        # Get video
        video_data = get_episode_video(anime_data, episode_num)
        
        episode_data = {
            'title': f"{anime_data.get('judul', 'Unknown')} - Episode {episode_num}",
            'anime_url': anime_slug,
            'anime_title': anime_data.get('judul', 'Unknown'),
            'episode': episode_num,
            'video_data': video_data,
            'prev_episode': int(episode_num) - 1 if episode_num.isdigit() and int(episode_num) > 1 else None,
            'next_episode': int(episode_num) + 1 if episode_num.isdigit() else None,
        }
        
        return render_template('watch.html', episode=episode_data)
        
    except Exception:
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
    except Exception:
        return render_template('genre.html', 
                             data=[], 
                             genre_name=genre_name, 
                             current_page=page,
                             max_pages=MAX_PAGES)

@app.route('/cache/reload')
def reload_cache():
    """Reload anime cache"""
    global anime_cache, cache_loaded
    anime_cache = []
    cache_loaded = False
    
    # Load di background thread
    def reload_in_background():
        load_all_anime()
    
    thread = threading.Thread(target=reload_in_background, daemon=True)
    thread.start()
    
    return jsonify({
        'status': 'success',
        'message': 'Cache reload started in background',
        'cache_size_before': len(anime_cache),
        'timestamp': datetime.now().isoformat()
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
            'cache_max_pages': CACHE_MAX_PAGES,
            'api_base': API_BASE,
            'last_updated': datetime.now().isoformat()
        }
    })

@app.route('/health')
def health_check():
    """Health check endpoint untuk Railway"""
    return jsonify({
        'status': 'healthy',
        'service': 'anime-streaming-api',
        'timestamp': datetime.now().isoformat(),
        'cache_status': 'loaded' if cache_loaded else 'loading',
        'cache_size': len(anime_cache),
        'max_pages_supported': MAX_PAGES
    })

@app.route('/stats')
def stats():
    """Server statistics"""
    load_all_anime()
    
    stats_data = {
        'server': {
            'max_pages': MAX_PAGES,
            'cache_size': len(anime_cache),
            'cache_loaded': cache_loaded,
            'cache_max_pages': CACHE_MAX_PAGES,
            'api_base': API_BASE,
            'server_time': datetime.now().isoformat()
        },
        'endpoints': {
            'home': '/',
            'ongoing': '/ongoing',
            'completed': '/completed',
            'movie': '/movie',
            'search': '/search?q=query',
            'anime_detail': '/anime/slug',
            'watch': '/watch/slug/episode-N',
            'genre': '/genre/genre-name',
            'cache_info': '/cache/info',
            'health': '/health'
        }
    }
    
    return jsonify(stats_data)

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

# ==================== STARTUP CACHE LOADING ====================

def load_startup_cache():
    """Load cache saat aplikasi dimulai"""
    log_info("Starting background cache loading at startup...")
    def load_cache_background():
        log_info("Loading anime cache in background...")
        load_all_anime()
    
    thread = threading.Thread(target=load_cache_background, daemon=True)
    thread.start()

# Panggil fungsi load cache saat startup
load_startup_cache()

# ==================== MAIN EXECUTION ====================

if __name__ == '__main__':
    # Dapatkan port dari environment variable (Railway menyediakan PORT)
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 60)
    print("🚀 ANIME STREAMING SERVER - 100 PAGE SUPPORT")
    print("=" * 60)
    print(f"📊 Max Pages: {MAX_PAGES}")
    print(f"📦 Cache Max Pages: {CACHE_MAX_PAGES}")
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
    print("   Cache Info:  http://localhost:5000/cache/info")
    print("   Stats:       http://localhost:5000/stats")
    print("=" * 60)
    
    # Run server
    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.environ.get('DEBUG', 'False').lower() == 'true',
        threaded=True
    )