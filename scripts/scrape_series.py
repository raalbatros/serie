#!/usr/bin/env python3
"""
IPTV Series M3U Scraper
Collects TV series (Turkish & International) from TMDB and generates M3U playlist.
Runs nightly via GitHub Actions.
"""

import os
import json
import time
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path

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

TMDB_HEADERS = {}
if TMDB_READ_TOKEN:
    TMDB_HEADERS["Authorization"] = f"Bearer {TMDB_READ_TOKEN}"

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


# ─── Link builder ─────────────────────────────────────────────────────────────

def build_stream_links(tmdb_id: int, imdb_id: str | None) -> list[dict]:
    links = []
    for src in STREAM_SOURCES:
        url_tmpl = src["url"]
        if "{imdb_id}" in url_tmpl and not imdb_id:
            continue
        url = url_tmpl.format(tmdb_id=tmdb_id, imdb_id=imdb_id or "")
        links.append({"source": src["name"], "url": url})
    return links


# ─── M3U builder ──────────────────────────────────────────────────────────────

def build_m3u(series_list: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "#EXTM3U",
        f'#PLAYLIST:IPTV Series — {now}',
        f"# Generated: {now}",
        f"# Total series: {len(series_list)}",
        f"# Includes: Yerli (TR) + Yabancı diziler",
        f"# Sources: {', '.join(s['name'] for s in STREAM_SOURCES)}",
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

    return f"""# 📺 IPTV Series Playlist

Yerli ve yabancı dizileri kapsayan, her gece otomatik güncellenen M3U playlist.

## Stats
| Metric | Value |
|--------|-------|
| **Toplam dizi** | {len(series_list)} |
| **Son güncelleme** | {generated_at} |
| **Dil kaynakları** | {len(LANGUAGES)} dil |
| **Stream kaynakları** | {len(STREAM_SOURCES)} sağlayıcı |

## Playlist URL
```
https://raw.githubusercontent.com/raalbatros/movie/main/output/series.m3u
```

## Dil / Kategori Dağılımı
| Kategori | Dizi Sayısı |
|----------|-------------|
{lang_table}

## Stream Kaynakları
| Kaynak | Format |
|--------|--------|
{chr(10).join(f"| `{s['name']}` | Season/Episode destekli |" for s in STREAM_SOURCES)}

## Kullanım
- **Kodi** → PVR IPTV Simple → M3U URL
- **VLC** → Medya → Ağ Akışı Aç
- **IPTV Smarters** → M3U URL ekle
- **TiviMate** → Playlist ekle → M3U URL

> Her gece **02:00 UTC** (05:00 Türkiye) otomatik güncellenir.
"""


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not TMDB_API_KEY and not TMDB_READ_TOKEN:
        log.error("No TMDB credentials. Set TMDB_API_KEY or TMDB_READ_TOKEN.")
        raise SystemExit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    log.info("Starting IPTV Series scraper...")

    all_series: dict[int, dict] = {}

    # 1) Popüler ve top rated
    log.info("Fetching popular series...")
    for s in get_popular_series(pages=5):
        s["lang_group"] = "Popüler"
        all_series[s["id"]] = s

    log.info("Fetching top rated series...")
    for s in get_top_rated_series(pages=3):
        all_series.setdefault(s["id"], {**s, "lang_group": "Top Rated"})

    # 2) Dile göre
    for lang_code, lang_name in LANGUAGES:
        log.info(f"Fetching {lang_name} series ({lang_code})...")
        for s in get_series_by_language(lang_code, pages=PAGES_PER_SOURCE):
            if s["id"] not in all_series:
                s["lang_group"] = lang_name
                all_series[s["id"]] = s

    # 3) Türe göre (sadece eksik olanlar)
    for genre_id, genre_name in GENRES.items():
        log.info(f"Fetching genre: {genre_name}...")
        for s in get_series_by_genre(genre_id, pages=2):
            if s["id"] not in all_series:
                s["lang_group"] = genre_name
                all_series[s["id"]] = s

    log.info(f"Total unique series collected: {len(all_series)}")

    # 4) Detay + IMDB ID + stream linkler
    enriched: list[dict] = []
    total = len(all_series)

    for i, (tmdb_id, series) in enumerate(all_series.items(), 1):
        name = series.get("name") or series.get("original_name", "Unknown")

        if not series.get("poster_path"):
            continue

        log.info(f"[{i}/{total}] {name}")

        details = get_series_details(tmdb_id)
        if details:
            series["number_of_seasons"]  = details.get("number_of_seasons", 1)
            series["number_of_episodes"] = details.get("number_of_episodes", 1)
            ext_ids = details.get("external_ids", {})
            series["imdb_id"] = ext_ids.get("imdb_id", "")
        else:
            series["number_of_seasons"]  = 1
            series["number_of_episodes"] = 1
            series["imdb_id"] = ""

        series["stream_links"] = build_stream_links(tmdb_id, series.get("imdb_id"))
        enriched.append(series)

    # Popülariteye göre sırala
    enriched.sort(key=lambda s: s.get("popularity", 0), reverse=True)
    log.info(f"Enriched {len(enriched)} series")

    # 5) M3U yaz
    m3u_content = build_m3u(enriched)
    OUTPUT_M3U.write_text(m3u_content, encoding="utf-8")
    log.info(f"Wrote M3U → {OUTPUT_M3U} ({len(m3u_content):,} bytes)")

    # 6) JSON yaz
    json_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(enriched),
        "series": [
            {
                "id":               s["id"],
                "name":             s.get("name") or s.get("original_name"),
                "original_name":    s.get("original_name", ""),
                "year":             (s.get("first_air_date") or "")[:4],
                "rating":           round(s.get("vote_average", 0), 1),
                "votes":            s.get("vote_count", 0),
                "popularity":       round(s.get("popularity", 0), 2),
                "imdb_id":          s.get("imdb_id", ""),
                "seasons":          s.get("number_of_seasons", 1),
                "episodes":         s.get("number_of_episodes", 1),
                "poster":           f"https://image.tmdb.org/t/p/w300{s['poster_path']}" if s.get("poster_path") else "",
                "genres":           get_genre_names(s.get("genre_ids", [])),
                "overview":         s.get("overview", ""),
                "lang_group":       s.get("lang_group", ""),
                "stream_links":     s.get("stream_links", []),
            }
            for s in enriched
        ]
    }
    OUTPUT_JSON.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Wrote JSON → {OUTPUT_JSON}")

    # 7) README yaz
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    OUTPUT_README.write_text(build_readme(enriched, generated_at), encoding="utf-8")
    log.info(f"Wrote README → {OUTPUT_README}")

    log.info("Done! ✅")


if __name__ == "__main__":
    main()
