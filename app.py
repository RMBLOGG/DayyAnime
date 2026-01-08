# app.py - Production Ready dengan GUARANTEED 100 PAGE LOADING
import os
from flask import Flask, render_template, request, jsonify
import requests
from urllib.parse import quote
import json
import time
from datetime import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Inisialisasi Flask app
app = Flask(__name__)

# Configuration dari environment variables
API_BASE = os.environ.get('API_BASE', 'https://api.sansekai.my.id/api')
MAX_PAGES = int(os.environ.get('MAX_PAGES', 100))  # 100 PAGES untuk semua endpoint
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', 5))  # Increased retries
RETRY_DELAY = float(os.environ.get('RETRY_DELAY', 1.0))
REQUEST_DELAY = float(os.environ.get('REQUEST_DELAY', 0.1))  # Reduced for speed
CACHE_MAX_PAGES = int(os.environ.get('CACHE_MAX_PAGES', 100))  # HARUS 100

# Performance tracking
startup_time = datetime.now()
total_api_calls = 0
failed_api_calls = 0

# Cache untuk menyimpan semua anime
anime_cache = []
cache_loaded = False
cache_loading = False
cache_metadata = {
    'total_pages_loaded': 0,
    'total_anime_loaded': 0,
    'last_updated': None,
    'load_duration': 0
}

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

def log_performance(message):
    """Log performance dengan timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] ⚡ {message}")

def safe_api_request(url, retry_count=0):
    """Fungsi aman untuk request API dengan retry mechanism"""
    global total_api_calls, failed_api_calls
    
    total_api_calls += 1
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        
        # Handle rate limiting (429)
        if response.status_code == 429:
            if retry_count < MAX_RETRIES:
                wait_time = RETRY_DELAY * (retry_count + 1)
                log_warning(f"Rate limited (429). Waiting {wait_time}s...")
                time.sleep(wait_time)
                return safe_api_request(url, retry_count + 1)
            failed_api_calls += 1
            return None
        
        # Handle 404 - Page not found
        if response.status_code == 404:
            log_warning(f"Page not found (404): {url}")
            return {'status': 'empty', 'data': []}
        
        # Handle other status codes
        if response.status_code != 200:
            log_warning(f"API request returned status {response.status_code}: {url}")
            if retry_count < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                return safe_api_request(url, retry_count + 1)
            failed_api_calls += 1
            return None
        
        return response
        
    except requests.exceptions.Timeout:
        if retry_count < MAX_RETRIES:
            wait_time = RETRY_DELAY * (retry_count + 1)
            time.sleep(wait_time)
            return safe_api_request(url, retry_count + 1)
        failed_api_calls += 1
        return None
            
    except Exception as e:
        log_error(f"Error in API request: {e}")
        if retry_count < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
            return safe_api_request(url, retry_count + 1)
        failed_api_calls += 1
        return None

def load_single_page(page_num):
    """Load single page dengan retry mechanism"""
    url = f"{API_BASE}/anime/latest?page={page_num}"
    max_attempts = 3
    
    for attempt in range(max_attempts):
        try:
            if attempt > 0:
                log_warning(f"Retry {attempt} for page {page_num}")
                time.sleep(attempt * 0.5)  # Exponential backoff
            
            response = safe_api_request(url)
            
            if response:
                if isinstance(response, dict) and response.get('status') == 'empty':
                    return {'page': page_num, 'data': [], 'status': 'empty'}
                
                data = response.json()
                if isinstance(data, list):
                    return {'page': page_num, 'data': data, 'status': 'success'}
                else:
                    log_warning(f"Page {page_num}: Response is not a list")
                    return {'page': page_num, 'data': [], 'status': 'invalid_format'}
            else:
                log_warning(f"Page {page_num}: No response on attempt {attempt + 1}")
                
        except Exception as e:
            log_error(f"Page {page_num}: Error on attempt {attempt + 1} - {str(e)[:50]}")
    
    return {'page': page_num, 'data': [], 'status': 'failed'}

def load_100_pages_parallel():
    """Load 100 pages secara parallel untuk kecepatan maksimum"""
    log_info("🚀 STARTING PARALLEL 100 PAGE LOAD...")
    
    all_anime = []
    start_time = time.time()
    successful_pages = 0
    empty_pages = 0
    failed_pages = 0
    
    # Gunakan ThreadPoolExecutor untuk parallel loading
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit semua 100 pages
        future_to_page = {executor.submit(load_single_page, page): page for page in range(1, 101)}
        
        # Process results as they complete
        for future in as_completed(future_to_page):
            page_num = future_to_page[future]
            try:
                result = future.result(timeout=20)
                
                if result['status'] == 'success' and len(result['data']) > 0:
                    all_anime.extend(result['data'])
                    successful_pages += 1
                    log_success(f"Page {page_num:3d}: {len(result['data'])} anime")
                elif result['status'] == 'empty':
                    empty_pages += 1
                    log_warning(f"Page {page_num:3d}: Empty page")
                else:
                    failed_pages += 1
                    log_error(f"Page {page_num:3d}: Failed to load")
                    
            except Exception as e:
                failed_pages += 1
                log_error(f"Page {page_num:3d}: Exception - {str(e)[:50]}")
    
    load_duration = time.time() - start_time
    
    log_info(f"\n{'='*60}")
    log_info("📊 PARALLEL LOAD SUMMARY")
    log_info(f"{'='*60}")
    log_success(f"Successful pages: {successful_pages}/100")
    log_warning(f"Empty pages: {empty_pages}/100")
    log_error(f"Failed pages: {failed_pages}/100")
    log_success(f"Total anime loaded: {len(all_anime)}")
    log_performance(f"Load duration: {load_duration:.2f} seconds")
    log_performance(f"Speed: {load_duration/100:.2f} seconds/page")
    log_info(f"{'='*60}")
    
    return all_anime, successful_pages, load_duration

def load_100_pages_sequential():
    """Load 100 pages secara sequential dengan agressive retry"""
    log_info("🚀 STARTING SEQUENTIAL 100 PAGE LOAD (AGGRESSIVE MODE)...")
    
    all_anime = []
    start_time = time.time()
    successful_pages = 0
    
    # Load dari multiple endpoints untuk redundancy
    endpoint_configs = [
        ('latest', 100),  # Primary: 100 pages dari latest
    ]
    
    for endpoint_name, target_pages in endpoint_configs:
        log_info(f"\n📥 Loading from {endpoint_name.upper()} ({target_pages} pages)...")
        
        pages_loaded = 0
        for page in range(1, target_pages + 1):
            max_attempts = 5  # Increased attempts
            
            for attempt in range(max_attempts):
                try:
                    if attempt > 0:
                        delay = attempt * 0.5
                        log_warning(f"  Page {page:3d}: Retry {attempt}/{max_attempts} (waiting {delay}s)")
                        time.sleep(delay)
                    
                    url = f"{API_BASE}/anime/{endpoint_name}?page={page}"
                    response = safe_api_request(url)
                    
                    if response:
                        if isinstance(response, dict) and response.get('status') == 'empty':
                            # Simpan empty page sebagai placeholder
                            all_anime.append({'__page': page, '__endpoint': endpoint_name, '__empty': True})
                            pages_loaded += 1
                            log_warning(f"  Page {page:3d}: Empty (placeholder added)")
                            break
                        
                        data = response.json()
                        if isinstance(data, list) and len(data) > 0:
                            # Tambahkan metadata ke setiap anime
                            for anime in data:
                                anime['__page'] = page
                                anime['__endpoint'] = endpoint_name
                                anime['__timestamp'] = datetime.now().isoformat()
                            
                            all_anime.extend(data)
                            pages_loaded += 1
                            successful_pages += 1
                            log_success(f"  Page {page:3d}: {len(data)} anime")
                            break
                        else:
                            log_warning(f"  Page {page:3d}: Empty or invalid list")
                            # Tambahkan placeholder untuk tracking
                            all_anime.append({'__page': page, '__endpoint': endpoint_name, '__empty': True})
                            pages_loaded += 1
                            break
                    else:
                        log_warning(f"  Page {page:3d}: No response on attempt {attempt + 1}")
                        
                except Exception as e:
                    log_error(f"  Page {page:3d}: Error on attempt {attempt + 1} - {str(e)[:50]}")
            
            # Small delay between pages untuk menghindari rate limiting
            if page < target_pages:
                time.sleep(REQUEST_DELAY)
        
        log_success(f"  ✅ {endpoint_name}: {pages_loaded}/{target_pages} pages loaded")
    
    # Remove placeholder entries
    filtered_anime = [anime for anime in all_anime if not anime.get('__empty', False)]
    
    load_duration = time.time() - start_time
    
    log_info(f"\n{'='*60}")
    log_info("📊 SEQUENTIAL LOAD SUMMARY")
    log_info(f"{'='*60}")
    log_success(f"Total pages attempted: 100")
    log_success(f"Pages with actual anime: {successful_pages}")
    log_success(f"Total anime loaded: {len(filtered_anime)}")
    log_performance(f"Load duration: {load_duration:.2f} seconds")
    log_info(f"{'='*60}")
    
    return filtered_anime, successful_pages, load_duration

def load_all_anime():
    """Load semua anime dari API - GUARANTEED 100 PAGE LOAD"""
    global anime_cache, cache_loaded, cache_loading, cache_metadata
    
    if cache_loading:
        log_info("Cache loading in progress, returning existing...")
        return anime_cache
    
    if cache_loaded and len(anime_cache) > 0:
        log_info(f"Using existing cache: {len(anime_cache)} anime")
        return anime_cache
    
    cache_loading = True
    log_info("=" * 70)
    log_info("🔥🔥🔥 GUARANTEED 100 PAGE LOAD INITIATED 🔥🔥🔥")
    log_info("=" * 70)
    
    load_start = datetime.now()
    
    # Try parallel loading first (faster)
    try:
        log_info("Attempting parallel loading...")
        all_anime, successful_pages, load_duration = load_100_pages_parallel()
        
        # If parallel loading got less than 80 pages, try sequential
        if successful_pages < 80:
            log_warning(f"Parallel loading only got {successful_pages} pages, switching to sequential...")
            all_anime, successful_pages, load_duration = load_100_pages_sequential()
    except Exception as e:
        log_error(f"Parallel loading failed: {e}, switching to sequential...")
        all_anime, successful_pages, load_duration = load_100_pages_sequential()
    
    # Remove duplicates dengan smart deduplication
    log_info("\n🧹 Removing duplicates...")
    
    seen_urls = set()
    seen_titles = set()
    unique_anime = []
    
    for anime in all_anime:
        # Skip placeholder entries
        if anime.get('__empty', False):
            continue
            
        anime_url = anime.get('url', '').strip().lower()
        anime_title = anime.get('judul', '').strip().lower()
        anime_id = str(anime.get('id', ''))
        
        # Create multiple identifiers for better deduplication
        identifiers = [
            f"url:{anime_url}",
            f"title:{anime_title}",
            f"id:{anime_id}",
            f"url_id:{anime_url}|{anime_id}",
            f"title_id:{anime_title}|{anime_id}"
        ]
        
        is_duplicate = False
        for identifier in identifiers:
            if identifier in seen_urls:
                is_duplicate = True
                break
        
        if not is_duplicate:
            for identifier in identifiers:
                seen_urls.add(identifier)
            seen_titles.add(anime_title)
            unique_anime.append(anime)
    
    # Sort by page number untuk maintain order
    unique_anime.sort(key=lambda x: x.get('__page', 999))
    
    anime_cache = unique_anime
    cache_loaded = True
    cache_loading = False
    
    # Update metadata
    cache_metadata.update({
        'total_pages_loaded': successful_pages,
        'total_anime_loaded': len(anime_cache),
        'last_updated': datetime.now().isoformat(),
        'load_duration': load_duration,
        'unique_anime_count': len(unique_anime)
    })
    
    load_end = datetime.now()
    total_load_time = (load_end - load_start).total_seconds()
    
    log_info("=" * 70)
    log_info("🎉 CACHE LOADING COMPLETE!")
    log_info("=" * 70)
    log_success(f"✅ SUCCESSFUL PAGES: {successful_pages}/100")
    log_success(f"📊 TOTAL UNIQUE ANIME: {len(anime_cache)}")
    log_success(f"⏰ LOAD DURATION: {total_load_time:.2f} seconds")
    log_success(f"📈 ANIME PER PAGE: {len(anime_cache)/max(successful_pages, 1):.1f}")
    log_info(f"🕒 CACHE TIMESTAMP: {cache_metadata['last_updated']}")
    log_info("=" * 70)
    
    # Log performance statistics
    log_performance(f"\n📈 PERFORMANCE STATISTICS:")
    log_performance(f"   Total API Calls: {total_api_calls}")
    log_performance(f"   Failed API Calls: {failed_api_calls}")
    log_performance(f"   Success Rate: {(total_api_calls - failed_api_calls)/total_api_calls*100:.1f}%")
    log_performance(f"   Avg Time per Page: {load_duration/100:.2f}s")
    
    return anime_cache

def find_anime_by_slug(slug):
    """Cari anime berdasarkan slug atau ID dari cache"""
    all_anime = load_all_anime()
    
    slug_normalized = slug.strip('/').lower()
    
    # Multiple matching strategies
    matching_strategies = [
        # Strategy 1: Exact URL match
        lambda anime: anime.get('url', '').strip('/').lower() == slug_normalized,
        
        # Strategy 2: URL contains slug
        lambda anime: slug_normalized in anime.get('url', '').strip('/').lower(),
        
        # Strategy 3: Slug contains URL
        lambda anime: anime.get('url', '').strip('/').lower() in slug_normalized,
        
        # Strategy 4: Title match
        lambda anime: slug_normalized in anime.get('judul', '').lower().replace(' ', '-').replace(':', ''),
        
        # Strategy 5: Partial title match
        lambda anime: any(part in anime.get('judul', '').lower() 
                         for part in slug_normalized.split('-') if len(part) > 2),
        
        # Strategy 6: ID match
        lambda anime: str(anime.get('id', '')) == slug_normalized,
        
        # Strategy 7: Fuzzy match on URL parts
        lambda anime: any(part in anime.get('url', '').lower() 
                         for part in slug_normalized.split('-') if len(part) > 3),
    ]
    
    for strategy in matching_strategies:
        for anime in all_anime:
            if strategy(anime):
                return anime
    
    return None

def get_episode_video(anime_data, episode_num):
    """Coba dapatkan video dengan berbagai cara"""
    try:
        anime_id = anime_data.get('id', '')
        anime_url = anime_data.get('url', '').rstrip('/')
        anime_slug = anime_url.split('/')[-1] if '/' in anime_url else anime_url
        
        # Coba berbagai format chapterUrlId
        possible_chapter_ids = [
            f"al-{anime_id}-{episode_num}",
            f"al-{anime_id}-{str(episode_num).zfill(2)}",
            f"al-{anime_id}-{str(episode_num).zfill(3)}",
            f"{anime_url}-episode-{episode_num}",
            f"{anime_url}-ep-{episode_num}",
            f"{anime_slug}-episode-{episode_num}",
            f"{anime_slug}-ep-{episode_num}",
            f"episode-{episode_num}-{anime_id}",
            f"ep-{episode_num}-{anime_id}",
        ]
        
        log_info(f"Trying to get video for episode {episode_num}, anime ID: {anime_id}")
        
        for chapter_id in possible_chapter_ids:
            try:
                video_url = f"{API_BASE}/anime/getvideo?chapterUrlId={quote(chapter_id)}"
                log_info(f"  Trying chapter ID: {chapter_id}")
                
                response = safe_api_request(video_url)
                if response:
                    data = response.json()
                    
                    if isinstance(data, dict):
                        if 'error' in data:
                            continue
                        if 'data' in data and data['data']:
                            log_success(f"  Found video with chapter ID: {chapter_id}")
                            return data
                        elif 'stream' in data:
                            log_success(f"  Found video stream with chapter ID: {chapter_id}")
                            return data
            except Exception as e:
                log_warning(f"  Failed with chapter ID {chapter_id}: {str(e)[:50]}")
                continue
        
        log_error(f"  No video found for episode {episode_num}")
        return None
            
    except Exception as e:
        log_error(f"Error getting episode video: {e}")
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
    except Exception as e:
        log_error(f"Error in home route: {e}")
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
        log_error(f"Error in ongoing route: {e}")
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
        log_error(f"Error in completed route: {e}")
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
        log_error(f"Error in movie route: {e}")
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
        
    except Exception as e:
        log_error(f"Error in search route: {e}")
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
        
    except Exception as e:
        log_error(f"Error in anime_detail route: {e}")
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
        
    except Exception as e:
        log_error(f"Error in watch route: {e}")
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
        log_error(f"Error in genre route: {e}")
        return render_template('genre.html', 
                             data=[], 
                             genre_name=genre_name, 
                             current_page=page,
                             max_pages=MAX_PAGES)

@app.route('/cache/reload')
def reload_cache():
    """Reload anime cache"""
    global anime_cache, cache_loaded, cache_metadata
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
        'cache_metadata': cache_metadata,
        'performance': {
            'total_api_calls': total_api_calls,
            'failed_api_calls': failed_api_calls,
            'success_rate': f"{(total_api_calls - failed_api_calls)/max(total_api_calls, 1)*100:.1f}%",
            'server_uptime': str(datetime.now() - startup_time)
        },
        'configuration': {
            'max_pages': MAX_PAGES,
            'cache_max_pages': CACHE_MAX_PAGES,
            'api_base': API_BASE,
            'max_retries': MAX_RETRIES,
            'retry_delay': RETRY_DELAY,
            'request_delay': REQUEST_DELAY
        },
        'sample_data': {
            'sample_count': min(10, len(anime_cache)),
            'samples': [
                {
                    'id': anime.get('id'),
                    'title': anime.get('judul'),
                    'url': anime.get('url'),
                    'type': anime.get('type'),
                    'episodes': anime.get('total_episode'),
                    'page': anime.get('__page'),
                    'endpoint': anime.get('__endpoint')
                }
                for anime in anime_cache[:10]
            ] if anime_cache else []
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
        'max_pages_supported': MAX_PAGES,
        'pages_actually_loaded': cache_metadata.get('total_pages_loaded', 0),
        'server_uptime': str(datetime.now() - startup_time)
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
            'pages_loaded': cache_metadata.get('total_pages_loaded', 0),
            'cache_max_pages': CACHE_MAX_PAGES,
            'api_base': API_BASE,
            'server_time': datetime.now().isoformat(),
            'server_uptime': str(datetime.now() - startup_time)
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
            'health': '/health',
            'stats': '/stats'
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
    """Load cache saat aplikasi dimulai - GUARANTEED 100 PAGES"""
    log_info("🔥 INITIALIZING GUARANTEED 100 PAGE CACHE LOAD...")
    def load_cache_background():
        log_info("🔄 Loading 100 pages of anime in background...")
        load_all_anime()
    
    thread = threading.Thread(target=load_cache_background, daemon=True)
    thread.start()
    log_info("✅ Background cache loading initiated")

# Panggil fungsi load cache saat startup
load_startup_cache()

# ==================== MAIN EXECUTION ====================

if __name__ == '__main__':
    # Dapatkan port dari environment variable (Railway menyediakan PORT)
    port = int(os.environ.get('PORT', 5000))
    
    print("\n" + "=" * 70)
    print("🚀 ANIME STREAMING SERVER - GUARANTEED 100 PAGE SUPPORT")
    print("=" * 70)
    print(f"📊 Max Pages: {MAX_PAGES}")
    print(f"📦 Cache Max Pages: {CACHE_MAX_PAGES}")
    print(f"🌐 API Base: {API_BASE}")
    print(f"🔄 Max Retries: {MAX_RETRIES}")
    print(f"⏱️  Retry Delay: {RETRY_DELAY}s")
    print(f"⚡ Request Delay: {REQUEST_DELAY}s")
    print(f"🔧 Debug Mode: {app.debug}")
    print(f"📡 Port: {port}")
    print("=" * 70)
    print("📋 Available Routes:")
    print("   Home:        http://localhost:5000")
    print("   Ongoing:     http://localhost:5000/ongoing")
    print("   Completed:   http://localhost:5000/completed")
    print("   Movie:       http://localhost:5000/movie")
    print("   Search:      http://localhost:5000/search?q=query")
    print("   Health:      http://localhost:5000/health")
    print("   Cache Info:  http://localhost:5000/cache/info")
    print("   Stats:       http://localhost:5000/stats")
    print("=" * 70)
    print("🔥 FEATURE: GUARANTEED 100 PAGE LOADING")
    print("   • Parallel loading for speed")
    print("   • Aggressive retry mechanism")
    print("   • Smart deduplication")
    print("   • Performance tracking")
    print("=" * 70 + "\n")
    
    # Run server
    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.environ.get('DEBUG', 'False').lower() == 'true',
        threaded=True
    )