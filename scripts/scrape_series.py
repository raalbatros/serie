#!/usr/bin/env python3
import os
import json
import time
import logging
import requests
import re
import random
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus
from typing import List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
OUTPUT_DIR = Path("output")
OUTPUT_M3U = OUTPUT_DIR / "series.m3u"
WORKING_SOURCES_FILE = OUTPUT_DIR / "working_sources.json"

LANGUAGES = [("tr", "Yerli"), ("en", "Yabancı"), ("ko", "Kore"), ("ja", "Japon")]
PAGES_PER_SOURCE = 2
REQUEST_DELAY = 0.25

STREAM_SOURCES = [
    "https://vidsrc.to/embed/tv/{tmdb_id}/1/1",
    "https://vidsrc.me/embed/tv?tmdb={tmdb_id}&season=1&episode=1",
    "https://multiembed.mov/?video_id={tmdb_id}&tmdb=1&s=1&e=1"
]

class LinkFinder:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self.working = self._load()
    
    def _load(self):
        try:
            if WORKING_SOURCES_FILE.exists():
                return json.load(open(WORKING_SOURCES_FILE))
        except:
            pass
        return {}
    
    def _save(self):
        json.dump(self.working, open(WORKING_SOURCES_FILE, "w"), indent=2)
    
    def check(self, url, timeout=8):
        try:
            r = self.session.get(url, timeout=timeout)
            return r.status_code < 400
        except:
            return False
    
    def find(self, tmdb_id, series_name):
        cache_key = str(tmdb_id)
        if cache_key in self.working and self.check(self.working[cache_key]):
            return self.working[cache_key]
        
        for src in STREAM_SOURCES:
            url = src.format(tmdb_id=tmdb_id)
            if self.check(url):
                self.working[cache_key] = url
                self._save()
                return url
        
        try:
            search_url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(series_name + ' izle')}"
            r = self.session.get(search_url, timeout=10)
            urls = re.findall(r'https?://[^\s<>"\']+', r.text)
            for url in urls:
                if any(x in url for x in ["embed", "video", "dizi"]):
                    if self.check(url):
                        self.working[cache_key] = url
                        self._save()
                        return url
        except:
            pass
        
        return None

def tmdb_get(path, params=None):
    params = params or {}
    params["api_key"] = TMDB_API_KEY
    try:
        r = requests.get(f"https://api.themoviedb.org/3{path}", params=params, timeout=10)
        return r.json()
    except:
        return None

def main():
    if not TMDB_API_KEY:
        log.error("TMDB_API_KEY missing")
        return 1
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    log.info("Starting...")
    
    all_ids = set()
    series_data = []
    finder = LinkFinder()
    
    for lang_code, lang_name in LANGUAGES:
        log.info(f"Fetching {lang_name}...")
        data = tmdb_get("/discover/tv", {"with_original_language": lang_code, "language": "tr-TR", "page": 1})
        if data:
            for item in data.get("results", []):
                if item["id"] not in all_ids and item.get("poster_path"):
                    all_ids.add(item["id"])
                    link = finder.find(item["id"], item.get("name") or item.get("original_name", ""))
                    if link:
                        series_data.append({
                            "id": item["id"],
                            "name": item.get("name") or item.get("original_name"),
                            "group": lang_name,
                            "url": link,
                            "poster": f"https://image.tmdb.org/t/p/w200{item['poster_path']}"
                        })
        time.sleep(REQUEST_DELAY)
    
    log.info(f"Found {len(series_data)} series")
    
    # M3U oluştur
    lines = ["#EXTM3U", "#PLAYLIST:IPTV Series Auto-Healing", ""]
    for s in series_data:
        lines.append(f'#EXTINF:-1 tvg-id="{s["id"]}" tvg-name="{s["name"]}" tvg-logo="{s["poster"]}" group-title="{s["group"]}",{s["name"]}')
        lines.append(s["url"])
        lines.append("")
    
    OUTPUT_M3U.write_text("\n".join(lines))
    log.info(f"Saved {len(series_data)} series to {OUTPUT_M3U}")
    log.info("Done!")
    return 0

if __name__ == "__main__":
    exit(main())
