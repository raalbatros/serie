const axios = require('axios');
const fs = require('fs');

const API_KEY = process.env.TMDB_API_KEY;

if (!API_KEY) {
    console.error("❌ TMDB API anahtarı bulunamadı!");
    process.exit(1);
}

if (!fs.existsSync('diziler')) {
    fs.mkdirSync('diziler');
}

const VIDMODY_TV_URL = "https://vidmody.com/tv";
const processedSeries = new Set();
const failedLinks = new Set();

// Tür ID'leri ve Türkçe isimleri
const GENRES = {
    10759: "Aksiyon & Macera",
    16: "Animasyon",
    35: "Komedi",
    80: "Suç",
    99: "Belgesel",
    18: "Dram",
    10751: "Aile",
    10762: "Çocuk",
    9648: "Gizem",
    10763: "Haber",
    10764: "Realite",
    10765: "Bilim Kurgu & Fantastik",
    10766: "Pembe Dizi",
    10767: "Talk Show",
    10768: "Savaş & Politika",
    37: "Western"
};

// Tür ikonları
const GENRE_ICONS = {
    "Aksiyon & Macera": "💥",
    "Komedi": "😂",
    "Dram": "🎭",
    "Suç": "🔫",
    "Bilim Kurgu & Fantastik": "🚀",
    "Gizem": "🔍",
    "Animasyon": "🐭",
    "Aile": "👨‍👩‍👧",
    "Belgesel": "🎥",
    "Savaş & Politika": "⚔️",
    "Pembe Dizi": "💕",
    "Western": "🤠"
};

async function getTvDetails(tmdbId) {
    try {
        const url = `https://api.themoviedb.org/3/tv/${tmdbId}?api_key=${API_KEY}&language=tr`;
        const response = await axios.get(url);
        const genreNames = response.data.genres.map(g => g.name);
        const mainGenre = genreNames[0] || "Diğer";
        return {
            name: response.data.name,
            firstAirYear: response.data.first_air_date ? response.data.first_air_date.split('-')[0] : "Bilinmiyor",
            genres: genreNames,
            mainGenre: mainGenre,
            poster: response.data.poster_path ? `https://image.tmdb.org/t/p/w500${response.data.poster_path}` : "",
            voteAverage: response.data.vote_average || 0
        };
    } catch {
        return null;
    }
}

async function checkLink(url) {
    if (failedLinks.has(url)) return false;
    try {
        await axios.head(url, { timeout: 5000 });
        return true;
    } catch {
        failedLinks.add(url);
        return false;
    }
}

async function scrapeSeries() {
    console.log("📺 DİZİ ARŞİVİ TARANIYOR...\n");
    const series = [];
    
    // Popüler dizileri çek (sayfa sayfa)
    console.log("🔥 Popüler diziler taranıyor...");
    
    for (let page = 1; page <= 20; page++) {
        const url = `https://api.themoviedb.org/3/tv/popular?api_key=${API_KEY}&language=tr&page=${page}`;
        
        try {
            const response = await axios.get(url);
            if (response.data.results.length === 0) break;
            
            for (const tv of response.data.results) {
                if (processedSeries.has(tv.id)) continue;
                
                const link = `${VIDMODY_TV_URL}/${tv.id}`;
                if (await checkLink(link)) {
                    const details = await getTvDetails(tv.id);
                    if (details) {
                        series.push({
                            id: tv.id,
                            name: details.name,
                            year: details.firstAirYear,
                            link: link,
                            poster: details.poster,
                            rating: details.voteAverage,
                            mainGenre: details.mainGenre,
                            allGenres: details.genres
                        });
                        processedSeries.add(tv.id);
                        console.log(`   ✓ ${details.name} (${details.firstAirYear}) [${details.mainGenre}] ⭐ ${details.voteAverage}`);
                    }
                }
                await new Promise(r => setTimeout(r, 50));
            }
        } catch(e) { 
            console.log(`   Sayfa ${page} hatası: ${e.message}`);
            break; 
        }
    }
    
    // Yayında olan diziler
    console.log("\n📺 Yayındaki diziler taranıyor...");
    
    for (let page = 1; page <= 10; page++) {
        const url = `https://api.themoviedb.org/3/tv/on_the_air?api_key=${API_KEY}&language=tr&page=${page}`;
        
        try {
            const response = await axios.get(url);
            if (response.data.results.length === 0) break;
            
            for (const tv of response.data.results) {
                if (processedSeries.has(tv.id)) continue;
                
                const link = `${VIDMODY_TV_URL}/${tv.id}`;
                if (await checkLink(link)) {
                    const details = await getTvDetails(tv.id);
                    if (details) {
                        series.push({
                            id: tv.id,
                            name: details.name,
                            year: details.firstAirYear,
                            link: link,
                            poster: details.poster,
                            rating: details.voteAverage,
                            mainGenre: details.mainGenre,
                            allGenres: details.genres
                        });
                        processedSeries.add(tv.id);
                        console.log(`   ✓ ${details.name} (${details.firstAirYear} - YAYINDA) [${details.mainGenre}] ⭐ ${details.voteAverage}`);
                    }
                }
                await new Promise(r => setTimeout(r, 50));
            }
        } catch(e) { break; }
    }
    
    // En çok oy alan diziler
    console.log("\n⭐ En çok oy alan diziler taranıyor...");
    
    for (let page = 1; page <= 10; page++) {
        const url = `https://api.themoviedb.org/3/tv/top_rated?api_key=${API_KEY}&language=tr&page=${page}`;
        
        try {
            const response = await axios.get(url);
            if (response.data.results.length === 0) break;
            
            for (const tv of response.data.results) {
                if (processedSeries.has(tv.id)) continue;
                
                const link = `${VIDMODY_TV_URL}/${tv.id}`;
                if (await checkLink(link)) {
                    const details = await getTvDetails(tv.id);
                    if (details) {
                        series.push({
                            id: tv.id,
                            name: details.name,
                            year: details.firstAirYear,
                            link: link,
                            poster: details.poster,
                            rating: details.voteAverage,
                            mainGenre: details.mainGenre,
                            allGenres: details.genres
                        });
                        processedSeries.add(tv.id);
                        console.log(`   ✓ ${details.name} (${details.firstAirYear}) [${details.mainGenre}] ⭐ ${details.voteAverage}`);
                    }
                }
                await new Promise(r => setTimeout(r, 50));
            }
        } catch(e) { break; }
    }
    
    console.log(`\n📊 Toplam taranan dizi: ${series.length}`);
    
    // ========== M3U OLUŞTUR (TÜRLERE GÖRE) ==========
    let m3u = '#EXTM3U\n';
    m3u += `# Dizi Arşivi - ${new Date().toLocaleDateString('tr-TR')}\n`;
    m3u += `# Toplam: ${series.length} dizi\n`;
    m3u += `# ⭐ IMDb puanına göre sıralanmıştır\n\n`;
    
    // Yayındaki diziler (özel)
    const onAir = series.filter(s => s.year !== "Bilinmiyor");
    const others = series.filter(s => s.year === "Bilinmiyor");
    
    if (onAir.length > 0) {
        onAir.sort((a, b) => b.rating - a.rating);
        m3u += `# 📺 YAYINDAKİ DİZİLER (${onAir.length} adet)\n`;
        for (const s of onAir.slice(0, 50)) {
            m3u += `#EXTINF:-1 group-title="Yayındaki Diziler" tvg-logo="${s.poster}", ${s.name} (${s.year}) ⭐ ${s.rating}\n`;
            m3u += `${s.link}\n`;
        }
        m3u += `\n`;
    }
    
    // Diğer dizileri türlerine göre grupla
    const seriesByGenre = {};
    
    for (const serie of others) {
        const genre = serie.mainGenre;
        if (!seriesByGenre[genre]) seriesByGenre[genre] = [];
        seriesByGenre[genre].push(serie);
    }
    
    const sortedGenres = Object.keys(seriesByGenre).sort((a, b) => seriesByGenre[b].length - seriesByGenre[a].length);
    
    for (const genre of sortedGenres) {
        const genreSeries = seriesByGenre[genre];
        genreSeries.sort((a, b) => b.rating - a.rating);
        
        const icon = GENRE_ICONS[genre] || "📺";
        
        m3u += `# ${icon} ${genre.toUpperCase()} (${genreSeries.length} adet)\n`;
        
        for (const s of genreSeries) {
            const yearInfo = s.year !== "Bilinmiyor" ? ` (${s.year})` : "";
            m3u += `#EXTINF:-1 group-title="${genre}" tvg-logo="${s.poster}", ${s.name}${yearInfo} ⭐ ${s.rating}\n`;
            m3u += `${s.link}\n`;
        }
        m3u += `\n`;
    }
    
    fs.writeFileSync('diziler/series.m3u', m3u);
    
    console.log(`\n✅ TAMAMLANDI!`);
    console.log(`📊 Toplam dizi: ${series.length}`);
    console.log(`🎭 Türler: ${sortedGenres.length} farklı kategori`);
    console.log(`💾 Kaydedildi: diziler/series.m3u`);
}

scrapeSeries().catch(console.error);
