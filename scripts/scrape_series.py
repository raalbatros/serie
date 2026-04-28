#!/usr/bin/env python3
"""
IPTV Series M3U Scraper + Auto-Healing
Collects TV series (Turkish & International) from TMDB and generates M3U playlist.
Automatically finds alternative links when sources are dead.
Runs nightly via GitHub Actions.
"""

import os
import json
import time
import logging
import requests
import re
import random
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus
from typing import List, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

TMDB_API_KEY    = os.getenv("TMDB_API_KEY", "")
TMDB_READ_TOKEN = os.getenv("TMDB_READ_TOKEN", "")
OUTPUT_DIR      = Path("output")
OUTPUT_M3U      = OUTPUT_DIR / "series.m3u"
OUTPUT_JSON     = OUTPUT_DIR / "series.json"
OUTPUT_README   = OUTPUT_DIR / "README.md"
WORKING_SOURCES_FILE = OUTPUT_DIR / "working_sources.json"
FAILED_SOURCES_FILE  = OUTPUT_DIR / "failed_sources.json"

# TV Genres
GENRES = {
    10759: "Action & Adventure",
    16:    "Animation",
    35:    "Comedy",
    80:    "Crime",
    99:    "Documentary",
    18:    "Drama",
    10751: "Family",
    10762: "Kids",
    9648:  "Mystery",
    10763: "News",
    10764: "Reality",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap",
    10767: "Talk",
    10768: "War & Politics",
    37:    "Western",
}

# Yerli + yabancı diller
LANGUAGES = [
    ("tr", "Yerli"),       # Türkçe
    ("en", "Yabancı"),     # İngilizce
    ("ko", "Kore"),        # Korece
    ("ja", "Japon"),       # Japonca
    ("es", "İspanyol"),    # İspanyolca
    ("de", "Alman"),       # Almanca
    ("fr", "Fransız"),     # Fransızca
    ("it", "İtalyan"),     # İtalyanca
]

PAGES_PER_SOURCE = 3
MIN_VOTE_COUNT   = 20
REQUEST_DELAY    = 0.25

# Stream kaynakları — dizi için season ve episode destekli
STREAM_SOURCES = [
    {"name": "vidsrc.to",    "url": "https://vidsrc.to/embed/tv/{tmdb_id}/1/1"},
    {"name": "vidsrc.me",    "url": "https://vidsrc.me/embed/tv?tmdb={tmdb_id}&season=1&episode=1"},
    {"name": "embed.su",     "url": "https://embed.su/embed/tv/{imdb_id}/1/1"},
    {"name": "multiembed",   "url": "https://multiembed.mov/?tmdb=1&video_id={tmdb_id}&s=1&e=1"},
    {"name": "videasy",      "url": "https://player.videasy.net/tv/{imdb_id}/1/1"},
    {"name": "2embed",       "url": "https://www.2embed.cc/embedtv/{imdb_id}&s=1&e=1"},
    {"name": "smashystream", "url": "https://player.smashy.stream/tv/{imdb_id}?s=1&e=1"},
]

# Alternatif kaynaklar için arama domainleri (otomatik keşif için)
SEARCH_DOMAINS = [
    "diziyou.net", "yabancidizi.org", "dizilab.com", "dizilla.club",
    "diziay.com", "dizikral.com", "videoseed.to", "vidsrc.xyz"
]

TMDB_HEADERS = {}
if TMDB_READ_TOKEN:
    TMDB_HEADERS["Authorization"] = f"Bearer {TMDB_READ_TOKEN}"

# ─── Auto-Healing Class ───────────────────────────────────────────────────────

class AutoHealingLinkFinder:
    """Ölü linkleri otomatik bulan ve iyileştiren sınıf"""
    
    def __init__(self):
        self.session = self._create_session()
        self.working_sources = self._load_working_sources()
        self.failed_sources = self._load_failed_sources()
        
    def _create_session(self):
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        return session
    
    def _load_working_sources(self):
        try:
            if WORKING_SOURCES_FILE.exists():
                with open(WORKING_SOURCES_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    def _load_failed_sources(self):
        try:
            if FAILED_SOURCES_FILE.exists():
                with open(FAILED_SOURCES_FILE, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {"failed_links": [], "retry_after": {}}
    
    def _save_working_sources(self):
        with open(WORKING_SOURCES_FILE, 'w') as f:
            json.dump(self.working_sources, f, indent=2)
    
    def _save_failed_sources(self):
        with open(FAILED_SOURCES_FILE, 'w') as f:
            json.dump(self.failed_sources, f, indent=2)
    
    def check_link_health(self, url: str, timeout: int = 10) -> bool:
        """Linkin çalışıp çalışmadığını kontrol et"""
        try:
            response = self.session.get(url, timeout=timeout, allow_redirects=True)
            return 200 <= response.status_code < 400
        except:
            return False
    
    def search_alternative(self, series_name: str, tmdb_id: int, imdb_id: str, season: int = 1, episode: int = 1) -> List[str]:
        """Otomatik alternatif link ara"""
        alternatives = []
        
        # Farklı arama sorguları
        queries = [
            f"{series_name} sezon {season} bölüm {episode} izle",
            f"{series_name} s{season}e{episode} watch",
            f"{series_name} episode {episode} season {season} online",
            f'"{series_name}" "bölüm {episode}" izle',
            f"tmdb {tmdb_id} episode {episode} watch"
        ]
        
        for query in queries:
            # DuckDuckGo Lite üzerinden ara
            try:
                search_url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
                response = self.session.get(search_url, timeout=15)
                
                # Potansiyel video linklerini bul
                urls = re.findall(r'https?://[^\s<>"\']+\.(?:mp4|m3u8|html|php|embed)[^\s<>"\']*', response.text)
                
                for url in urls:
                    if any(domain in url for domain in SEARCH_DOMAINS + ['embed', 'video', 'player', 'watch']):
                        if self.check_link_health(url, timeout=5):
                            alternatives.append(url)
                            log.info(f"  ✅ Alternatif link bulundu: {url[:80]}...")
                            break
                            
            except Exception as e:
                pass
            
            time.sleep(random.uniform(0.5, 1))
        
        return list(set(alternatives))
    
    def try_generate_url_patterns(self, tmdb_id: int, imdb_id: str, season: int, episode: int) -> List[str]:
        """Farklı URL patternleri dene"""
        patterns = []
        
        if imdb_id:
            patterns.append(f"https://vidsrc.to/embed/tv/{imdb_id}/{season}/{episode}")
            patterns.append(f"https://player.smashy.stream/tv/{imdb_id}?s={season}&e={episode}")
            patterns.append(f"https://www.2embed.cc/embedtv/{imdb_id}&s={season}&e={episode}")
        
        patterns.append(f"https://multiembed.mov/?video_id={tmdb_id}&tmdb=1&s={season}&e={episode}")
        patterns.append(f"https://vidsrc.me/embed/tv?tmdb={tmdb_id}&season={season}&episode={episode}")
        patterns.append(f"https://embed.su/embed/tv/{tmdb_id}/{season}/{episode}")
        
        return patterns
    
    def get_working_link(self, series_name: str, tmdb_id: int, imdb_id: str = "", season: int = 1, episode: int = 1) -> Optional[str]:
        """Çalışan bir link bulana kadar dene"""
        
        cache_key = f"{tmdb_id}_{season}_{episode}"
        
        # Önce cache'deki çalışan linki kontrol et
        if cache_key in self.working_sources:
            cached_url = self.working_sources[cache_key]
            if self.check_link_health(cached_url):
                return cached_url
            else:
                # Ölü olduğu anlaşıldı, cacheden kaldır
                del self.working_sources[cache_key]
                self._save_working_sources()
        
        # 1. Mevcut kaynakları dene
        for src in STREAM_SOURCES:
            try:
                if "{imdb_id}" in src["url"] and not imdb_id:
                    continue
                url = src["url"].format(tmdb_id=tmdb_id, imdb_id=imdb_id or "")
                # Season/episode bilgisini güncelle
                url = url.replace("/1/1", f"/{season}/{episode}")
                url = url.replace("&s=1&e=1", f"&s={season}&e={episode}")
                url = url.replace("?s=1&e=1", f"?s={season}&e={season}")
                
                if self.check_link_health(url, timeout=5):
                    self.working_sources[cache_key] = url
                    self._save_working_sources()
                    return url
            except:
                continue
        
        # 2. URL patternlerini dene
        patterns = self.try_generate_url_patterns(tmdb_id, imdb_id, season, episode)
        for pattern in patterns:
            if self.check_link_health(pattern, timeout=5):
                self.working_sources[cache_key] = pattern
                self._save_working_sources()
                return pattern
        
        # 3. Otomatik arama
        log.info(f"  🔍 {series_name} S{season}E{episode} için alternatif aranıyor...")
        alternatives = self.search_alternative(series_name, tmdb_id, imdb_id, season, episode)
        
        for alt_url in alternatives[:10]:
            if self.check_link_health(alt_url, timeout=8):
                self.working_sources[cache_key] = alt_url
                self._save_working_sources()
                log.info(f"  🎉 Bulundu ve cache'e kaydedildi!")
                return alt_url
        
        log.warning(f"  ❌ {series_name} S{season}E{episode} için link bulunamadı")
        return None


# ─── TMDB helpers ─────────────────────────────────────────────────────────────

def tmdb_get(path: str, params: dict = None) -> dict | None:
    base = "https://api.themoviedb.org/3"
    if TMDB_API_KEY and not TMDB_READ_TOKEN:
        params = params or {}
        params["api_key"] = TMDB_API_KEY
    try:
        r = requests.get(f"{base}{path}", headers=TMDB_HEADERS, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"TMDB request failed ({path}): {e}")
        return None


def get_popular_series(pages: int = PAGES_PER_SOURCE) -> list[dict]:
    results = []
    for page in range(1, pages + 1):
        data = tmdb_get("/tv/popular", {"language": "tr-TR", "page": page})
        if not data:
            break
        results.extend(data.get("results", []))
        time.sleep(REQUEST_DELAY)
    return results


def get_top_rated_series(pages: int = PAGES_PER_SOURCE) -> list[dict]:
    results = []
    for page in range(1, pages + 1):
        data = tmdb_get("/tv/top_rated", {"language": "tr-TR", "page": page})
        if not data:
            break
        results.extend(data.get("results", []))
        time.sleep(REQUEST_DELAY)
    return results


def get_series_by_language(lang_code: str, pages: int = PAGES_PER_SOURCE) -> list[dict]:
    results = []
    for page in range(1, pages + 1):
        data = tmdb_get("/discover/tv", {
            "with_original_language": lang_code,
            "language":               "tr-TR",
            "sort_by":                "popularity.desc",
            "vote_count.gte":         MIN_VOTE_COUNT,
            "page":                   page,
        })
        if not data:
            break
        results.extend(data.get("results", []))
        time.sleep(REQUEST_DELAY)
    return results


def get_series_by_genre(genre_id: int, pages: int = 2) -> list[dict]:
    results = []
    for page in range(1, pages + 1):
        data = tmdb_get("/discover/tv", {
            "with_genres":    genre_id,
            "language":       "tr-TR",
            "sort_by":        "popularity.desc",
            "vote_count.gte": MIN_VOTE_COUNT,
            "page":           page,
        })
        if not data:
            break
        results.extend(data.get("results", []))
        time.sleep(REQUEST_DELAY)
    return results


def get_series_details(tmdb_id: int) -> dict | None:
    """Dizi detayları: sezon sayısı, bölüm sayısı, IMDB ID"""
    data = tmdb_get(f"/tv/{tmdb_id}", {"language": "tr-TR", "append_to_response": "external_ids"})
    time.sleep(REQUEST_DELAY)
    return data


def get_genre_names(genre_ids: list[int]) -> list[str]:
    return [GENRES.get(gid, "") for gid in genre_ids if gid in GENRES]


# ─── Link builder with Auto-Healing ───────────────────────────────────────────

def build_stream_links_with_healing(tmdb_id: int, imdb_id: str | None, series_name: str) -> list[dict]:
    """Auto-healing özellikli stream link builder"""
    links = []
    finder = AutoHealingLinkFinder()
    
    # Ana linki bul (1.sezon 1.bölüm için)
    main_url = finder.get_working_link(series_name, tmdb_id, imdb_id or "", 1, 1)
    
    if main_url:
        links.append({"source": "auto-healed", "url": main_url})
    else:
        # Fallback: varsayılan kaynakları dene
        for src in STREAM_SOURCES[:3]:
            try:
                if "{imdb_id}" in src["url"] and not imdb_id:
                    continue
                url = src["url"].format(tmdb_id=tmdb_id, imdb_id=imdb_id or "")
                links.append({"source": src["name"], "url": url})
            except:
                continue
    
    return links


# ─── M3U builder ──────────────────────────────────────────────────────────────

def build_m3u(series_list: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "#EXTM3U",
        f'#PLAYLIST:IPTV Series — {now}',
        f"# Generated: {now}",
        f"# Total series: {len(series_list)}",
        f"# Auto-healing: ENABLED",
        f"# Sources: {', '.join(s['name'] for s in STREAM_SOURCES)} + auto-discovery",
        "",
    ]

    for s in series_list:
        name        = s.get("name") or s.get("original_name", "Unknown")
        first_air   = (s.get("first_air_date") or "")[:4]
        rating      = round(s.get("vote_average", 0), 1)
        tmdb_id     = s["id"]
        imdb_id     = s.get("imdb_id", "")
        poster      = f"https://image.tmdb.org/t/p/w300{s['poster_path']}" if s.get("poster_path") else ""
        genres_str  = "/".join(get_genre_names(s.get("genre_ids", [])))
        group       = s.get("lang_group", genres_str.split("/")[0] if genres_str else "Dizi")
        seasons     = s.get("number_of_seasons", 1)
        episodes    = s.get("number_of_episodes", 1)
        links       = s.get("stream_links", [])
        best_url    = links[0]["url"] if links else f"https://vidsrc.to/embed/tv/{tmdb_id}/1/1"

        label = f"{name} ({first_air})"
        if seasons > 1:
            label += f" [{seasons} Sezon]"
        label += f" [{rating}⭐]"

        extinf = (
            f'#EXTINF:-1 '
            f'tvg-id="{tmdb_id}" '
            f'tvg-name="{name}" '
            f'tvg-logo="{poster}" '
            f'group-title="{group}" '
            f'tmdb-id="{tmdb_id}" '
            f'imdb-id="{imdb_id}" '
            f'rating="{rating}" '
            f'year="{first_air}" '
            f'seasons="{seasons}" '
            f'episodes="{episodes}",'
            f'{label}'
        )
        lines.append(extinf)
        lines.append(best_url)
        lines.append("")

    return "\n".join(lines)


# ─── README builder ───────────────────────────────────────────────────────────

def build_readme(series_list: list[dict], generated_at: str) -> str:
    lang_counts: dict[str, int] = {}
    for s in series_list:
        g = s.get("lang_group", "Diğer")
        lang_counts[g] = lang_counts.get(g, 0) + 1

    lang_table = "\n".join(
        f"| {g} | {c} |"
        for g, c in sorted(lang_counts.items(), key=lambda x: -x[1])
    )

    return f"""# 📺 IPTV Series Playlist (Auto-Healing)

Yerli ve yabancı dizileri kapsayan, her gece otomatik güncellenen M3U playlist.
**Özellik:** Ölü linkler otomatik tespit edilip yenileri aranır.

## Stats
| Metric | Value |
|--------|-------|
| **Toplam dizi** | {len(series_list)} |
| **Son güncelleme** | {generated_at} |
| **Dil kaynakları** | {len(LANGUAGES)} dil |
| **Stream kaynakları** | {len(STREAM_SOURCES)} sağlayıcı |
| **Auto-Healing** | ✅ Aktif |

## Playlist URL
