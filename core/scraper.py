import requests
import json
import os
from datetime import datetime

class IDX80Scraper:
    """
    The Source of Truth for the Wintra Project.
    Attempts to fetch live IDX80 constituents but defaults to the 
    Integrated April-May 2026 Watchlist on failure.
    """
    def __init__(self, data_path="data/idx80_list.json"):
        self.data_path = data_path
        self.api_url = "https://www.idx.co.id/primary/Index/GetConstituent?indexCode=IDX80&language=en-us"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest"
        }
        self.data_path = data_path
        
        # --- [HARDCODED BACKUP: APRIL-MAY 2026 INTEGRATED WATCHLIST] ---
        self.backup_list = [
            # Core IDX80 (Current)
            'ADRO', 'AKRA', 'AMMN', 'AMRT', 'ANTM', 'ARTO', 'ASII', 'BBCA', 'BBNI', 
            'BBRI', 'BBTN', 'BMRI', 'BRMS', 'BRPT', 'BSDE', 'BTPS', 'BUKA', 'BUMI', 
            'CMRY', 'CPIN', 'CTRA', 'CUAN', 'DSNG', 'ELSA', 'EMTK', 'ENRG', 'ERAA', 
            'ESSA', 'EXCL', 'GOTO', 'HEAL', 'HRUM', 'ICBP', 'INCO', 'INDF', 'INDY', 
            'INKP', 'INTP', 'ISAT', 'ITMG', 'JPFA', 'JSMR', 'KIJA', 'KLBF', 'KPIG', 
            'MAPA', 'MAPI', 'MBMA', 'MDKA', 'MEDC', 'MIKA', 'MTEL', 'MYOR', 'NCKL', 
            'PANI', 'PGAS', 'PGEO', 'PNLF', 'PTBA', 'PTRO', 'PWON', 'RAJA', 'RATU', 
            'SCMA', 'SIDO', 'SMGR', 'SMRA', 'SSIA', 'TAPG', 'TLKM', 'TOWR', 'UNTR', 
            'UNVR', 'WIFI', 'BREN', 'DSSA', 
            
            # May 4 Entrants (Index Rebalancing Plays)
            'DEWA', 'GGRM', 'TPIA', 'BKSL', 'CBDK', 
            
            # Momentum Wildcards (ARA Radars)
            'PPRE', 'KOTA', 'WIKA', 'PTPP', 'ADMR'
        ]
        
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)

    def fetch_live(self):
        """Attempts to reach the IDX API."""
        print("📡 Attempting live IDX API sync...")
        try:
            # Note: We expect this might return 403 for now until TLS impersonation is fully tuned
            response = requests.get(self.api_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json().get('data', [])
            tickers = [s['Symbol'] for s in data if 'Symbol' in s]
            
            if tickers:
                print(f"✅ Live sync successful. Found {len(tickers)} tickers.")
                return sorted(tickers)
            return None
        except Exception as e:
            print(f"⚠️ Live sync failed ({e}). Reverting to Integrated Backup.")
            return None

    def sync(self):
        """Orchestrates the fetch and persistence."""
        tickers = self.fetch_live()
        
        # If live fails, use the hardcoded backup
        is_backup = False
        if not tickers:
            tickers = sorted(self.backup_list)
            is_backup = True
        
        # Save to JSON for the Engine to consume
        metadata = {
            "updated_at": datetime.now().isoformat(),
            "source": "Integrated Backup" if is_backup else "IDX API",
            "count": len(tickers),
            "tickers": tickers
        }
        
        with open(self.data_path, 'w') as f:
            json.dump(metadata, f, indent=4)
        
        print(f"💾 Synced {len(tickers)} tickers to {self.data_path}")
        return tickers

if __name__ == "__main__":
    scraper = IDX80Scraper()
    scraper.sync()