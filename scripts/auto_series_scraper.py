import requests
import re
import json
import time
import random
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

class AutoSeriesScraper:
    def __init__(self):
        self.session = self._create_session()
        self.working_sources = self._load_working_sources()
        self.failed_sources = self._load_failed_sources()
        
    def _create_session(self):
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        return session
    
    def _load_working_sources(self):
        """Çalışan kaynakları yükle"""
        try:
            with open('output/working_sources.json', 'r') as f:
                return json.load(f)
        except:
            return {}
    
    def _load_failed_sources(self):
        """Başarısız kaynakları yükle"""
        try:
            with open('output/failed_sources.json', 'r') as f:
                return json.load(f)
        except:
            return {"failed_links": [], "retry_after": {}}
    
    def check_link_health(self, url: str) -> bool:
        """Linkin çalışıp çalışmadığını kontrol et"""
        try:
            response = self.session.get(url, timeout=10, allow_redirects=True)
            # 200-299 arası başarılı, 404/403/500 ise ölü
            return 200 <= response.status_code < 300
        except:
            return False
    
    def search_alternative(self, series_name: str, season: int, episode: int) -> List[str]:
        """Google/DuckDuckGo üzerinden alternatif link ara"""
        alternatives = []
        
        # Aramak için farklı sorgu kalıpları
        queries = [
            f"{series_name} season {season} episode {episode} izle",
            f"{series_name} s{season}e{episode} watch online",
            f"{series_name} {season}. sezon {episode}. bölüm embed",
            f'"{series_name}" "bölüm {episode}" izle'
        ]
        
        for query in queries:
            # DuckDuckGo lite (daha basit, blocking yapmaz)
            try:
                search_url = f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}"
                response = self.session.get(search_url, timeout=15)
                
                # Sonuçlardan potansiyel video linklerini bul
                urls = re.findall(r'https?://[^\s<>"\']+\.(?:mp4|m3u8|html|php)[^\s<>"\']*', response.text)
                
                for url in urls:
                    if any(domain in url for domain in ['diziyou', 'dizilab', 'yabancidizi', 'embed']):
                        alternatives.append(url)
                        
            except:
                pass
            
            time.sleep(random.uniform(1, 3))  # Rate limiting'e takılmamak için
        
        return list(set(alternatives))  # Tekrarları temizle
    
    def auto_discover_working_links(self, series_name: str, season: int, episode: int) -> Optional[str]:
        """Otomatik olarak çalışan bir link bul"""
        
        # Önce daha önce çalışan kaynakları dene
        cache_key = f"{series_name}_{season}_{episode}"
        if cache_key in self.working_sources:
            # Önceden çalışan link hala çalışıyor mu?
            if self.check_link_health(self.working_sources[cache_key]):
                return self.working_sources[cache_key]
            else:
                # Artık çalışmıyor, cacheden kaldır
                del self.working_sources[cache_key]
        
        # Yeni alternatif ara
        print(f"🔍 {series_name} S{season}E{episode} için alternatif aranıyor...")
        potential_links = self.search_alternative(series_name, season, episode)
        
        # Paralel olarak linkleri test et
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_link = {
                executor.submit(self.check_link_health, link): link 
                for link in potential_links[:20]  # Max 20 link dene
            }
            
            for future in as_completed(future_to_link):
                link = future_to_link[future]
                if future.result():
                    print(f"✅ Çalışan link bulundu: {link}")
                    # Çalışan linki cache'e kaydet
                    self.working_sources[cache_key] = link
                    self._save_working_sources()
                    return link
        
        print(f"❌ {series_name} S{season}E{episode} için link bulunamadı")
        return None
    
    def _save_working_sources(self):
        """Çalışan linkleri kaydet"""
        with open('output/working_sources.json', 'w') as f:
            json.dump(self.working_sources, f, indent=2)
    
    def get_episode_link(self, series_name: str, season: int, episode: int) -> Optional[str]:
        """Ana fonksiyon - otomatik link getirir"""
        
        # Varsayılan pattern'leri dene (en hızlı yöntem)
        default_patterns = [
            f"https://diziyou.net/{series_name}-{season}-{episode}-izle",
            f"https://yabancidizi.org/{series_name}/sezon-{season}/bolum-{episode}",
            f"https://dizilab.com/{series_name}/sezon/{season}/bolum/{episode}",
        ]
        
        for pattern in default_patterns:
            if self.check_link_health(pattern):
                return pattern
        
        # Hiçbiri çalışmıyorsa otomatik keşfet
        return self.auto_discover_working_links(series_name, season, episode)


# Ana scrape fonksiyonu (mevcut scriptinizi değiştirmeden entegre edin)
def get_series_episodes(series_data):
    """
    Bu fonksiyonu mevcut scrape_series.py'ye entegre edin
    """
    scraper = AutoSeriesScraper()
    episodes_list = []
    
    for series in series_data:
        for season in range(1, series['seasons'] + 1):
            for episode in range(1, series['episodes_per_season'][season] + 1):
                link = scraper.get_episode_link(series['name'], season, episode)
                if link:
                    episodes_list.append({
                        'series': series['name'],
                        'season': season,
                        'episode': episode,
                        'url': link
                    })
                
                # Rate limiting
                time.sleep(random.uniform(0.5, 1.5))
    
    return episodes_list


if __name__ == "__main__":
    # Test
    tester = AutoSeriesScraper()
    test_link = tester.get_episode_link("The Last of Us", 1, 1)
    print(f"Test sonucu: {test_link}")
