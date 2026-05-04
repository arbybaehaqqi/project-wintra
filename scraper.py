import os
import json
import pandas as pd
import yfinance as yf
from datetime import datetime
import time

# ANSI Colors for Terminal
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

class IntradayScraper:
    """
    Fetches 60 days of 5-minute interval data for the IDX80 universe
    and caches it locally to prevent API bans and speed up model execution.
    """
    def __init__(self, cache_dir="core/data/intraday_cache", list_path="core/data/idx80_list.json"):
        self.cache_dir = cache_dir
        self.list_path = list_path
        
        # Ensure directories exist
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.list_path), exist_ok=True)
        
    def _ensure_universe_exists(self):
        """Creates a default IDX80 list if it doesn't exist."""
        if not os.path.exists(self.list_path):
            print(f"{YELLOW}⚠️ Universe file not found. Creating default IDX80 list...{RESET}")
            default_universe = {
                "tickers": ["BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ASII", "GOTO", "AMMN", "BREN", "SIDO", "DSNG", "MEDC", "PTBA", "ADRO", "ERAA"]
            }
            with open(self.list_path, 'w') as f:
                json.dump(default_universe, f, indent=4)
                
    def load_universe(self):
        self._ensure_universe_exists()
        with open(self.list_path, 'r') as f:
            data = json.load(f)
            return data.get('tickers', [])

    def get_cache_filename(self, ticker):
        """Generates a filename based on the ticker and today's date."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.cache_dir, f"{ticker}_5m_{today_str}.csv")

    def fetch_idx80_intraday(self):
        tickers = self.load_universe()
        
        print(f"\n{CYAN}🔄 WINTRA HIGH-RES SCRAPER (5-Minute Data){RESET}")
        print(f"Target: {len(tickers)} stocks | Lookback: 60 Days")
        print("─"*75)
        
        success_count = 0
        failed_tickers = []

        for idx, ticker in enumerate(tickers):
            symbol = f"{ticker}.JK"
            cache_file = self.get_cache_filename(ticker)
            
            # 1. Check Local Cache First
            if os.path.exists(cache_file):
                print(f" [{idx+1}/{len(tickers)}] {ticker:<6} | {GREEN}Loaded from Local Cache{RESET}")
                success_count += 1
                continue
                
            # 2. Fetch from Yahoo Finance
            try:
                print(f" [{idx+1}/{len(tickers)}] {ticker:<6} | 📡 Downloading...", end="")
                data = yf.download(symbol, period="60d", interval="5m", progress=False)
                
                # Handling yfinance multi-level columns
                if isinstance(data.columns, pd.MultiIndex):
                    data = data.xs(symbol, level=1, axis=1)

                if data.empty:
                    print(f"\r [{idx+1}/{len(tickers)}] {ticker:<6} | {YELLOW}⚠️ No Data Found{RESET}       ")
                    failed_tickers.append(ticker)
                else:
                    # --- STANDARDIZATION FIX ---
                    # Ensure the index is named properly
                    data.index.name = "Datetime"
                    
                    # Clean timezone
                    if data.index.tz is not None:
                        data.index = data.index.tz_localize(None)
                    
                    # Reset index to move Datetime into a column and save without index
                    # This guarantees the "Datetime" header exists in the CSV
                    data.reset_index(inplace=True)
                    data.to_csv(cache_file, index=False)
                    
                    print(f"\r [{idx+1}/{len(tickers)}] {ticker:<6} | {GREEN}✅ Saved Standardized ({len(data)} bars){RESET}")
                    success_count += 1
                    
                time.sleep(0.5)
                
            except Exception as e:
                print(f"\r [{idx+1}/{len(tickers)}] {ticker:<6} | {RED}❌ Fetch Error: {str(e)}{RESET}")
                failed_tickers.append(ticker)

        print("─"*75)
        print(f"✅ Scraping Complete. Success: {success_count} | Failed: {len(failed_tickers)}")
        if failed_tickers:
            print(f"Failed Tickers: {', '.join(failed_tickers)}")
        print("═"*75 + "\n")

if __name__ == "__main__":
    scraper = IntradayScraper()
    scraper.fetch_idx80_intraday()
