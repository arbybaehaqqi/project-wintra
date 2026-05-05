import os
import json
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import pytz
import time

# --- CONFIGURATION ---
BASE_DIR = "core/data"
LIST_PATH = f"{BASE_DIR}/idx80_list.json"
CACHE_DIR = f"{BASE_DIR}/master_ticker"
REQUIRED_COLUMNS = ["Datetime", "Open", "High", "Low", "Close", "Volume"]
LOOKBACK_DAYS = 58 

# ANSI Colors (Windows Compatible)
CYAN, GREEN, YELLOW, RED, MAGENTA, GRAY, RESET = "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[95m", "\033[90m", "\033[0m"

def update_universe_and_cache():
    if not os.path.exists(LIST_PATH):
        return False

    try:
        with open(LIST_PATH, 'r') as f:
            universe = json.load(f).get("tickers", [])
    except Exception:
        return False

    os.makedirs(CACHE_DIR, exist_ok=True)
    
    success_count = 0
    for idx, ticker in enumerate(universe):
        try:
            sym = f"{ticker}.JK"
            df = yf.download(sym, period=f"{LOOKBACK_DAYS}d", interval="5m", progress=False)

            if df.empty:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)

            # Force WIB
            if df.index.tz is not None:
                df.index = df.index.tz_convert('Asia/Jakarta').tz_localize(None)
            else:
                df.index = df.index + pd.Timedelta(hours=7)

            df.index.name = "Datetime"
            df.reset_index(inplace=True)
            
            # Integrity Check
            for col in REQUIRED_COLUMNS:
                if col not in df.columns: df[col] = 0.0
            
            df = df[REQUIRED_COLUMNS]
            df.to_csv(os.path.join(CACHE_DIR, f"{ticker}_5m.csv"), index=False)
            success_count += 1
            
            if idx % 20 == 0: time.sleep(1) 
        except:
            continue

    return True

if __name__ == "__main__":
    # Removed Emojis to fix Windows UnicodeEncodeError
    print(f"{CYAN}[WINTRA SYNC ACTIVE]{RESET}")
    if update_universe_and_cache():
        print(f"{GREEN}[SUCCESS] Sync Finished.{RESET}")
    else:
        print(f"{RED}[ERROR] Sync Failed.{RESET}")