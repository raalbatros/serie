def process_episode(dizi_adi, poster_url, bolum_url):
    full_url = absolute_url(bolum_url)
    stream = extract_stream(full_url)

    if not stream:
        return None

    sezon_match = re.search(r"/sezon-(\d+)/bolum-(\d+)/", full_url)

    if sezon_match:
        sezon, bolum = sezon_match.groups()
        baslik = f"{dizi_adi} S{sezon.zfill(2)}B{bolum.zfill(2)}"
    else:
        baslik = dizi_adi

    return make_entry(
        f"TR: {baslik}",
        poster_url,
        stream,
        "Dizi - HDFilmizle"
    )


def get_series_from_page(page_num):
    url = f"{BASE_URL}/yabanci-dizi-izle-2/page/{page_num}/"
    soup = get_soup(url)

    if not soup:
        print(f"[DIZI] Sayfa açılamadı: {url}")
        return []

    container = soup.find("div", id="moviesListResult")
    if not container:
        print(f"[DIZI] Liste bulunamadı: {url}")
        return []

    cards = container.find_all("a", class_="poster")
    entries = []

    for card in cards:
        try:
            dizi_url = absolute_url(card.get("href"))
            if not dizi_url:
                continue

            img = card.find("img", class_="lazyload")
            poster = absolute_url(
                img.get("data-src") or img.get("src") if img else ""
            )

            title_tag = card.find("h2", class_="title")
            dizi_adi = title_tag.text.strip() if title_tag else "Bilinmeyen Dizi"

            detail_soup = get_soup(dizi_url)
            if not detail_soup:
                continue

            episode_links = detail_soup.find_all(
                "a",
                href=re.compile(r"/dizi/[^/]+/sezon-\d+/bolum-\d+/?$")
            )

            seen = set()

            for ep in episode_links:
                href = ep.get("href")

                if not href or href in seen:
                    continue

                seen.add(href)

                entry = process_episode(dizi_adi, poster, href)
                if entry:
                    entries.append(entry)

        except Exception as e:
            print(f"[DIZI HATA] {card.get('href')}: {e}")

    return entries


def write_dizi_m3u(entries):
    unique_entries = []
    seen_streams = set()

    for entry in entries:
        lines = entry.strip().splitlines()
        stream = lines[-1] if lines else ""

        if not stream or stream in seen_streams:
            continue

        seen_streams.add(stream)
        unique_entries.append(entry)

    with open(DIZI_OUTPUT, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.writelines(unique_entries)

    print(f"[KAYIT] {DIZI_OUTPUT}: {len(unique_entries)} benzersiz dizi bölümü")
