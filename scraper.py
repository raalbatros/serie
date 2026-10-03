import os
import re
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://www.hdfilmizle.life"
OUTPUT_FILE = "hdfilmizle.m3u"

DIZI_BASLANGIC = int(os.getenv("DIZI_BASLANGIC", "1"))
DIZI_BITIS = int(os.getenv("DIZI_BITIS", "50"))

FILM_BASLANGIC = int(os.getenv("FILM_BASLANGIC", "1"))
FILM_BITIS = int(os.getenv("FILM_BITIS", "975"))

WORKER_COUNT = int(os.getenv("WORKER_COUNT", "8"))
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


def get_soup(url):
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, timeout=REQUEST_TIMEOUT)

            if r.status_code == 200:
                return BeautifulSoup(r.content, "lxml")

            if r.status_code in (403, 429, 503):
                wait = 5 * (attempt + 1)
                print(f"[BEKLE] {r.status_code} - {url} - {wait} sn")
                time.sleep(wait)
                continue

        except requests.RequestException as e:
            print(f"[HATA] {url}: {e}")
            time.sleep(3)

    return None


def absolute_url(path):
    if not path:
        return ""
    return path if path.startswith("http") else BASE_URL + path


def extract_stream(page_url):
    soup = get_soup(page_url)
    if not soup:
        return None

    iframe = soup.find("iframe", class_="vpx")
    if not iframe:
        return None

    src = iframe.get("data-src") or iframe.get("src")
    if not src or "vidrame.pro" not in src:
        return None

    vid_match = re.search(r"vidrame\.pro/vr/(?:get/)?([a-f0-9]{8})", src)
    if not vid_match:
        return None

    vid_id = vid_match.group(1)

    quality_match = re.search(r"/(\d+)\.txt", src)
    quality = quality_match.group(1) if quality_match else "1080"

    txt_url = f"https://vidrame.pro/vr/get/{vid_id}/{quality}.txt"

    try:
        r = session.get(txt_url, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None

        text = r.text.strip()

        m3u8_match = re.search(r'https?://[^\s"\']+\.m3u8[^\s"\']*', text)
        if m3u8_match:
            return m3u8_match.group(0)

        if text.startswith("#EXTM3U"):
            return txt_url

        return None

    except requests.RequestException:
        return None


def make_entry(title, poster, stream_url, group):
    title = re.sub(r'[\r\n"]+', " ", title).strip()
    poster = poster.replace('"', "")

    return (
        f'#EXTINF:-1 tvg-id="" tvg-name="{title}" '
        f'tvg-logo="{poster}" group-title="{group}",{title}\n'
        f"{stream_url}\n"
    )


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
                "a", href=re.compile(r"/sezon-\d+/bolum-\d+/")
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


def process_movie(card):
    try:
        title_tag = card.find("h2", class_="title")
        title = title_tag.text.strip() if title_tag else "Bilinmeyen Film"

        img = card.find("img", class_="lazyload")
        poster = absolute_url(
            img.get("data-src") or img.get("src") if img else ""
        )

        movie_url = absolute_url(card.get("href"))
        if not movie_url:
            return None

        stream = extract_stream(movie_url)
        if not stream:
            return None

        return make_entry(
            f"TR: {title}",
            poster,
            stream,
            "Film - HDFilmizle"
        )

    except Exception as e:
        print(f"[FILM HATA] {card.get('href')}: {e}")
        return None


def get_movies_from_page(page_num):
    url = f"{BASE_URL}/page/{page_num}/"
    soup = get_soup(url)

    if not soup:
        return []

    container = soup.find("div", id="moviesListResult")
    if not container:
        return []

    cards = container.find_all("a", class_="poster")
    entries = []

    for card in cards:
        entry = process_movie(card)
        if entry:
            entries.append(entry)

    return entries


def run_jobs(kind, start_page, end_page, worker_function):
    results = []

    with ThreadPoolExecutor(max_workers=WORKER_COUNT) as executor:
        futures = {
            executor.submit(worker_function, page): page
            for page in range(start_page, end_page + 1)
        }

        for future in as_completed(futures):
            page = futures[future]

            try:
                data = future.result()
                results.extend(data)
                print(f"[OK] {kind} sayfa {page}: {len(data)} kayıt")
            except Exception as e:
                print(f"[HATA] {kind} sayfa {page}: {e}")

    return results


def main():
    print("Tarama başlıyor...")

    series = run_jobs(
        "Dizi",
        DIZI_BASLANGIC,
        DIZI_BITIS,
        get_series_from_page
    )

    movies = run_jobs(
        "Film",
        FILM_BASLANGIC,
        FILM_BITIS,
        get_movies_from_page
    )

    all_entries = series + movies

    unique_entries = []
    seen_streams = set()

    for entry in all_entries:
        lines = entry.strip().splitlines()
        stream = lines[-1] if lines else ""

        if stream in seen_streams:
            continue

        seen_streams.add(stream)
        unique_entries.append(entry)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        f.writelines(unique_entries)

    print(f"Bitti. Toplam {len(unique_entries)} benzersiz kayıt yazıldı.")


if __name__ == "__main__":
    main()
