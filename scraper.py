def get_series_from_page(page_num):
    url = f"{BASE_URL}/yabanci-dizi-izle-2/page/{page_num}/"
    soup = get_soup(url)

    if not soup:
        return []

    container = soup.find("div", id="moviesListResult")
    if not container:
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
                "a", href=re.compile(r"/dizi/[^/]+/sezon-\d+/bolum-\d+/?$")
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
