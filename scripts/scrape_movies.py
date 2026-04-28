#!/usr/bin/env python3
import os, json, time, logging, requests
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

TMDB_API_KEY    = os.getenv("TMDB_API_KEY", "")
TMDB_READ_TOKEN = os.getenv("TMDB_READ_TOKEN", "")
OUTPUT_DIR      = Path("output")
OUTPUT_M3U      = OUTPUT_DIR / "series.m3u"
OUTPUT_JSON     = OUTPUT_DIR / "series.json"

GENRES = {10759:"Action & Adventure",16:"Animation",35:"Comedy",80:"Crime",18:"Drama",10751:"Family",9648:"Mystery",10765:"Sci-Fi & Fantasy",10768:"War & Politics",37:"Western"}
LANGUAGES = [("tr","Yerli"),("en","Yabancı"),("ko","Kore"),("ja","Japon"),("es","İspanyol"),("de","Alman"),("fr","Fransız"),("it","İtalyan")]
PAGES = 3
MIN_VOTES = 20
DELAY = 0.25
STREAM_SOURCES = [
    {"name":"vidsrc.to","url":"https://vidsrc.to/embed/tv/{tmdb_id}/1/1"},
    {"name":"vidsrc.me","url":"https://vidsrc.me/embed/tv?tmdb={tmdb_id}&season=1&episode=1"},
    {"name":"embed.su","url":"https://embed.su/embed/tv/{imdb_id}/1/1"},
    {"name":"multiembed","url":"https://multiembed.mov/?tmdb=1&video_id={tmdb_id}&s=1&e=1"},
    {"name":"videasy","url":"https://player.videasy.net/tv/{imdb_id}/1/1"},
]

HEADERS = {}
if TMDB_READ_TOKEN:
    HEADERS["Authorization"] = f"Bearer {TMDB_READ_TOKEN}"

def tmdb_get(path, params=None):
    if TMDB_API_KEY and not TMDB_READ_TOKEN:
        params = params or {}
        params["api_key"] = TMDB_API_KEY
    try:
        r = requests.get(f"https://api.themoviedb.org/3{path}", headers=HEADERS, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"Failed {path}: {e}")
        return None

def fetch(path, params, pages):
    results = []
    for page in range(1, pages+1):
        data = tmdb_get(path, {**params, "page": page})
        if data: results.extend(data.get("results", []))
        time.sleep(DELAY)
    return results

def get_imdb(tmdb_id):
    data = tmdb_get(f"/tv/{tmdb_id}", {"append_to_response": "external_ids"})
    time.sleep(DELAY)
    if data:
        ext = data.get("external_ids", {})
        return ext.get("imdb_id", ""), data.get("number_of_seasons", 1), data.get("number_of_episodes", 1)
    return "", 1, 1

def build_links(tmdb_id, imdb_id):
    links = []
    for s in STREAM_SOURCES:
        if "{imdb_id}" in s["url"] and not imdb_id:
            continue
        links.append({"source": s["name"], "url": s["url"].format(tmdb_id=tmdb_id, imdb_id=imdb_id or "")})
    return links

def genre_names(ids):
    return [GENRES[i] for i in ids if i in GENRES]

def main():
    if not TMDB_API_KEY and not TMDB_READ_TOKEN:
        log.error("No TMDB credentials!")
        raise SystemExit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    log.info("Starting series scraper...")

    all_series = {}

    for s in fetch("/tv/popular", {"language":"tr-TR"}, 5):
        s["lang_group"] = "Popüler"; all_series[s["id"]] = s
    for s in fetch("/tv/top_rated", {"language":"tr-TR"}, 3):
        all_series.setdefault(s["id"], {**s, "lang_group":"Top Rated"})
    for lang, name in LANGUAGES:
        for s in fetch("/discover/tv", {"with_original_language":lang,"language":"tr-TR","sort_by":"popularity.desc","vote_count.gte":MIN_VOTES}, PAGES):
            if s["id"] not in all_series:
                s["lang_group"] = name; all_series[s["id"]] = s
    for gid, gname in GENRES.items():
        for s in fetch("/discover/tv", {"with_genres":gid,"language":"tr-TR","sort_by":"popularity.desc","vote_count.gte":MIN_VOTES}, 2):
            if s["id"] not in all_series:
                s["lang_group"] = gname; all_series[s["id"]] = s

    log.info(f"Collected {len(all_series)} series")

    enriched = []
    total = len(all_series)
    for i, (tmdb_id, s) in enumerate(all_series.items(), 1):
        name = s.get("name") or s.get("original_name","?")
        if not s.get("poster_path"): continue
        log.info(f"[{i}/{total}] {name}")
        imdb_id, seasons, episodes = get_imdb(tmdb_id)
        s["imdb_id"] = imdb_id
        s["number_of_seasons"] = seasons
        s["number_of_episodes"] = episodes
        s["stream_links"] = build_links(tmdb_id, imdb_id)
        enriched.append(s)

    enriched.sort(key=lambda x: x.get("popularity", 0), reverse=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = ["#EXTM3U", f"# Generated: {now}", f"# Total: {len(enriched)}", ""]
    for s in enriched:
        name     = s.get("name") or s.get("original_name","?")
        year     = (s.get("first_air_date") or "")[:4]
        rating   = round(s.get("vote_average",0),1)
        tmdb_id  = s["id"]
        imdb_id  = s.get("imdb_id","")
        poster   = f"https://image.tmdb.org/t/p/w300{s['poster_path']}" if s.get("poster_path") else ""
        group    = s.get("lang_group","Dizi")
        seasons  = s.get("number_of_seasons",1)
        links    = s.get("stream_links",[])
        url      = links[0]["url"] if links else f"https://vidsrc.to/embed/tv/{tmdb_id}/1/1"
        label    = f"{name} ({year}) [{seasons} Sezon] [{rating}⭐]"
        lines.append(f'#EXTINF:-1 tvg-id="{tmdb_id}" tvg-name="{name}" tvg-logo="{poster}" group-title="{group}" imdb-id="{imdb_id}" seasons="{seasons}",{label}')
        lines.append(url)
        lines.append("")

    OUTPUT_M3U.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Wrote {OUTPUT_M3U}")

    json_data = {"generated_at": now, "total": len(enriched), "series": [
        {"id":s["id"],"name":s.get("name") or s.get("original_name"),"year":(s.get("first_air_date") or "")[:4],
         "rating":round(s.get("vote_average",0),1),"imdb_id":s.get("imdb_id",""),
         "seasons":s.get("number_of_seasons",1),"poster":f"https://image.tmdb.org/t/p/w300{s['poster_path']}" if s.get("poster_path") else "",
         "genres":genre_names(s.get("genre_ids",[])),"lang_group":s.get("lang_group",""),"stream_links":s.get("stream_links",[])}
        for s in enriched
    ]}
    OUTPUT_JSON.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Wrote {OUTPUT_JSON}")
    log.info("Done! ✅")

if __name__ == "__main__":
    main()
