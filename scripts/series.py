#!/usr/bin/env python3
"""
IPTV Series Scraper - Auto Link Finder
"""

import os
import json
import time
import requests
from datetime import datetime
from pathlib import Path

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
OUTPUT_DIR = Path("output")
OUTPUT_M3U = OUTPUT_DIR / "series.m3u"
CACHE_FILE = OUTPUT_DIR / "cache.json"

# Çalışan link provider'ları (sürekli güncellenir)
PROVIDERS = [
    "https://vidlink.pro/tv/{}/1/1",
    "https://vidsrc.net/embed/tv/{}/1/1",
    "https://multiembed.mov/?video_id={}&tmdb=1&s=1&e=1",
]

CATEGORIES = {
    "tr": "Yerli",
    "en": "Yabancı",
    "ko": "Kore",
    "ja": "Japon"
}

class LinkFinder:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        self.cache = self._load_cache()
    
    def _load_cache(self):
        if CACHE_FILE.exists():
            try:
                return json.load(open(CACHE_FILE))
            except:
                return {}
        return {}
    
    def _save_cache(self):
        json.dump(self.cache, open(CACHE_FILE, 'w'), indent=2)
    
    def _test_link(self, url):
        try:
            r = self.session.get(url, timeout=8)
            return r.status_code < 400
        except:
            return False
    
    def find(self, tmdb_id):
        tmdb_str = str(tmdb_id)
        
        if tmdb_str in self.cache and self._test_link(self.cache[tmdb_str]):
            return self.cache[tmdb_str]
        
        for provider in PROVIDERS:
            url = provider.format(tmdb_id)
            if self._test_link(url):
                self.cache[tmdb_str] = url
                self._save_cache()
                return url
        
        return None

def tmdb_get(path, params=None):
    if not TMDB_API_KEY:
        return None
    params = params or {}
    params["api_key"] = TMDB_API_KEY
    params["language"] = "tr-TR"
    try:
        r = requests.get(f"https://api.themoviedb.org/3{path}", params=params, timeout=10)
        return r.json()
    except:
        return None

def main():
    print("=" * 50)
    print("IPTV Series Scraper")
    print("=" * 50)
    
    if not TMDB_API_KEY:
        print("❌ TMDB_API_KEY bulunamadı!")
        return 1
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    finder = LinkFinder()
    all_series = []
    
    for lang_code, category in CATEGORIES.items():
        print(f"\n📺 {category} taranıyor...")
        
        data = tmdb_get("/discover/tv", {
            "with_original_language": lang_code,
            "sort_by": "popularity.desc",
            "vote_count.gte": 50,
            "page": 1
        })
        
        if not data:
            continue
        
        count = 0
        for series in data.get("results", []):
            if count >= 40:
                break
            if not series.get("poster_path"):
                continue
            
            tmdb_id = series["id"]
            name = series.get("name") or series.get("original_name", "Unknown")
            poster = f"https://image.tmdb.org/t/p/w200{series['poster_path']}"
            
            print(f"  {name[:35]}...", end=" ")
            video_url = finder.find(tmdb_id)
            
            if video_url:
                all_series.append({
                    "tmdb_id": tmdb_id,
                    "name": name,
                    "category": category,
                    "poster": poster,
                    "url": video_url
                })
                count += 1
                print("✅")
            else:
                print("❌")
            
            time.sleep(0.3)
    
    # M3U oluştur
    lines = ["#EXTM3U", f"# Total: {len(all_series)} series", ""]
    for s in all_series:
        lines.append(f'#EXTINF:-1 tvg-id="{s["tmdb_id"]}" tvg-name="{s["name"]}" tvg-logo="{s["poster"]}" group-title="{s["category"]}",{s["name"]}')
        lines.append(s["url"])
        lines.append("")
    
    OUTPUT_M3U.write_text("\n".join(lines))
    
    print(f"\n✅ {len(all_series)} dizi kaydedildi!")
    print(f"📁 {OUTPUT_M3U}")
    
    return 0

if __name__ == "__main__":
    exit(main())
