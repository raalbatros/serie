# 📺 IPTV Series M3U Auto-Updater

Yerli ve yabancı dizileri her gece otomatik toplayıp M3U playlist oluşturan GitHub Actions projesi.

## Özellikler

- **Yerli diziler** — Türkçe yapımlar (TR)
- **Yabancı diziler** — İngilizce, Korece, Japonca, İspanyolca, Almanca, Fransızca, İtalyanca
- **7 stream kaynağı** — Season/Episode destekli embed linkler
- **Her gece güncellenir** — 02:30 UTC (05:30 Türkiye)
- **Sezon & bölüm bilgisi** — M3U etiketlerinde gösterilir

## Kurulum

### 1. GitHub Secret ekle (aynı TMDB key'i kullan)

Repo → **Settings** → **Secrets and variables** → **Actions**

| Secret | Değer |
|--------|-------|
| `TMDB_API_KEY` | TMDB v3 key'in |

### 2. Dosyaları yükle

```
.github/workflows/nightly.yml
scripts/scrape_series.py
output/.gitkeep
requirements.txt
```

### 3. Actions'ı çalıştır

Actions → **Nightly Series M3U Update** → **Run workflow**

## Playlist URL

```
https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/output/series.m3u
```

## Kategoriler (M3U group-title)

| Kategori | Açıklama |
|----------|----------|
| Yerli | Türkçe yapımlar |
| Yabancı | İngilizce yapımlar |
| Kore | Kore dizileri |
| Japon | Japon dizileri (Anime dahil) |
| İspanyol | İspanyolca yapımlar |
| Alman | Almanca yapımlar |
| Fransız | Fransızca yapımlar |
| İtalyan | İtalyanca yapımlar |
| Popüler | TMDB popüler listesi |
| Top Rated | En yüksek puanlılar |

## Zamanlama

Her gece **02:30 UTC** = **05:30 Türkiye saati**

Film scraper'dan 30 dakika sonra çalışır, çakışma olmaz.
