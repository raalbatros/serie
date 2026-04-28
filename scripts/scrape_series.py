
## Dil / Kategori Dağılımı
| Kategori | Dizi Sayısı |
|----------|-------------|
{lang_table}

## Auto-Healing Özelliği
- Ölü linkleri otomatik tespit eder
- DuckDuckGo üzerinden alternatif kaynak arar
- Çalışan linkleri cache'ler
- Sonraki çalışmalarda hemen kullanır

## Kullanım
- **Kodi** -> PVR IPTV Simple -> M3U URL
- **VLC** -> Medya -> Ağ Akışı Aç
- **IPTV Smarters** -> M3U URL ekle
- **TiviMate** -> Playlist ekle -> M3U URL

> Her gece **02:00 UTC** (05:00 Türkiye) otomatik güncellenir.
"""

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not TMDB_API_KEY and not TMDB_READ_TOKEN:
        log.error("No TMDB credentials. Set TMDB_API_KEY or TMDB_READ_TOKEN.")
        raise SystemExit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    log.info("Starting IPTV Series scraper with AUTO-HEALING...")

    all_series: dict[int, dict] = {}

    log.info("Fetching popular series...")
    for s in get_popular_series(pages=5):
        s["lang_group"] = "Popüler"
        all_series[s["id"]] = s

    log.info("Fetching top rated series...")
    for s in get_top_rated_series(pages=3):
        all_series.setdefault(s["id"], {**s, "lang_group": "Top Rated"})

    for lang_code, lang_name in LANGUAGES:
        log.info(f"Fetching {lang_name} series ({lang_code})...")
        for s in get_series_by_language(lang_code, pages=PAGES_PER_SOURCE):
            if s["id"] not in all_series:
                s["lang_group"] = lang_name
                all_series[s["id"]] = s

    for genre_id, genre_name in GENRES.items():
        log.info(f"Fetching genre: {genre_name}...")
        for s in get_series_by_genre(genre_id, pages=2):
            if s["id"] not in all_series:
                s["lang_group"] = genre_name
                all_series[s["id"]] = s

    log.info(f"Total unique series collected: {len(all_series)}")

    enriched: list[dict] = []
    total = len(all_series)

    for i, (tmdb_id, series) in enumerate(all_series.items(), 1):
        name = series.get("name") or series.get("original_name", "Unknown")
        poster_path = series.get("poster_path")
        if not poster_path:
            log.debug(f"[{i}/{total}] Skipping {name} (no poster)")
            continue
        log.info(f"[{i}/{total}] {name}")
        details = get_series_details(tmdb_id)
        if details:
            series["number_of_seasons"] = details.get("number_of_seasons", 1)
            series["number_of_episodes"] = details.get("number_of_episodes", 1)
            ext_ids = details.get("external_ids", {})
            series["imdb_id"] = ext_ids.get("imdb_id", "")
        else:
            series["number_of_seasons"] = 1
            series["number_of_episodes"] = 1
            series["imdb_id"] = ""
        series["stream_links"] = build_stream_links_with_healing(tmdb_id, series.get("imdb_id"), name)
        enriched.append(series)

    enriched.sort(key=lambda s: s.get("popularity", 0), reverse=True)
    log.info(f"Enriched {len(enriched)} series with auto-healing")

    m3u_content = build_m3u(enriched)
    OUTPUT_M3U.write_text(m3u_content, encoding="utf-8")
    log.info(f"Wrote M3U -> {OUTPUT_M3U} ({len(m3u_content):,} bytes)")

    json_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "auto_healing_enabled": True,
        "total": len(enriched),
        "series": [
            {
                "id": s["id"],
                "name": s.get("name") or s.get("original_name"),
                "original_name": s.get("original_name", ""),
                "year": (s.get("first_air_date") or "")[:4],
                "rating": round(s.get("vote_average", 0), 1),
                "votes": s.get("vote_count", 0),
                "popularity": round(s.get("popularity", 0), 2),
                "imdb_id": s.get("imdb_id", ""),
                "seasons": s.get("number_of_seasons", 1),
                "episodes": s.get("number_of_episodes", 1),
                "poster": f"https://image.tmdb.org/t/p/w300{s['poster_path']}" if s.get("poster_path") else "",
                "genres": get_genre_names(s.get("genre_ids", [])),
                "overview": s.get("overview", ""),
                "lang_group": s.get("lang_group", ""),
                "stream_links": s.get("stream_links", []),
            }
            for s in enriched
        ]
    }
    OUTPUT_JSON.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Wrote JSON -> {OUTPUT_JSON}")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    OUTPUT_README.write_text(build_readme(enriched, generated_at), encoding="utf-8")
    log.info(f"Wrote README -> {OUTPUT_README}")

    healing_stats = {
        "total_series": len(enriched),
        "cached_links": len(AutoHealingLinkFinder().working_sources),
        "last_run": generated_at
    }
    stats_file = OUTPUT_DIR / "healing_stats.json"
    stats_file.write_text(json.dumps(healing_stats, indent=2), encoding="utf-8")

    log.info("Done! ✅ Auto-healing aktif!")

if __name__ == "__main__":
    main()
