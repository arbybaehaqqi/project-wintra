import os
import shutil
import sys
import pandas as pd
import yfinance as yf
import subprocess

# --- CONFIGURATION ---
OLD_CACHE_NAME = "intraday_cache"
NEW_CACHE_NAME = "master_ticker"

FILE_RELOCATION = {
    "scraper_intraday.py": "tools/data_manager", # Updated from scraper.py
    "scraper_daily.py": "tools/data_manager",
    "cache_cleaner.py": "tools/data_manager",
    "sys_sync.py": "tools/data_manager",
    "wintra_db_diag.py": "tools/data_manager",
    "project_verify.py": "tools/data_manager",
    "optimize_m1.py": "tools/optimization",
    "intraday_report.py": "reports",
    "morning_report.py": "reports",
    "messenger.py": "reports",
    "test_m1.py": "tests",
    "test_swing.py": "tests"
}

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def create_dirs():
    dirs = [
        "tools/data_manager", "tools/optimization", "reports", "tests", "logs", 
        f"core/data/{NEW_CACHE_NAME}/daily", 
        f"core/data/{NEW_CACHE_NAME}/intraday"
    ]
    for d in dirs:
        path = os.path.join(ROOT_DIR, d)
        if not os.path.exists(path):
            os.makedirs(path)

def migrate_files():
    print("[*] Relocating tool scripts...")
    for filename, target_dir in FILE_RELOCATION.items():
        sources = [os.path.join(ROOT_DIR, filename), os.path.join(ROOT_DIR, "tools", filename)]
        for src in sources:
            if os.path.exists(src):
                dest_dir = os.path.join(ROOT_DIR, target_dir)
                try:
                    shutil.move(src, os.path.join(dest_dir, filename))
                except Exception: pass

def migrate_data_architecture():
    base_cache = os.path.join(ROOT_DIR, "core", "data", NEW_CACHE_NAME)
    intraday_dir = os.path.join(base_cache, "intraday")
    
    if not os.path.exists(base_cache): return
    
    moved = 0
    for file in os.listdir(base_cache):
        if file.endswith("5m.csv"):
            src = os.path.join(base_cache, file)
            dst = os.path.join(intraday_dir, file)
            shutil.move(src, dst)
            moved += 1
    if moved > 0:
        print(f"    [+] Moved {moved} legacy intraday files to 'intraday/' folder.")

def get_latest_local_date_from_csv(folder_path):
    """Reads the actual last Datetime entry INSIDE the CSV file."""
    latest_date = None
    if not os.path.exists(folder_path): return None
    
    for file in os.listdir(folder_path):
        if file.endswith(".csv"):
            try:
                # Read the CSV to find the true last recorded market date
                df = pd.read_csv(os.path.join(folder_path, file))
                if 'Datetime' in df.columns and not df.empty:
                    # Strip timezones and extract just the Date
                    file_latest = pd.to_datetime(df['Datetime'].iloc[-1]).tz_localize(None).date()
                    if latest_date is None or file_latest > latest_date:
                        latest_date = file_latest
            except Exception: 
                pass
            
            # We only need to check one valid file to know the folder's sync status
            if latest_date:
                break 
                
    return latest_date

def check_data_updates():
    print("\n[*] Pinging yfinance for latest market data...")
    try:
        # Check BBCA.JK as a reliable bellwether for the Indonesian market
        ticker = yf.Ticker("BBCA.JK")
        latest_market_data = ticker.history(period="1d")
        if latest_market_data.empty:
            print("    [!] Could not connect to yfinance.")
            return
            
        latest_market_date = latest_market_data.index[-1].tz_localize(None).date()
        print(f"    -> Latest IDX Market Date is: {latest_market_date}")
        
        daily_dir = os.path.join(ROOT_DIR, "core", "data", NEW_CACHE_NAME, "daily")
        intraday_dir = os.path.join(ROOT_DIR, "core", "data", NEW_CACHE_NAME, "intraday")
        
        local_daily_date = get_latest_local_date_from_csv(daily_dir)
        local_intra_date = get_latest_local_date_from_csv(intraday_dir)

        # --- 1. DAILY PROMPT ---
        print("\n--- Daily Data Status ---")
        if local_daily_date is None or local_daily_date < latest_market_date:
            print(f"    Local Daily Date   : {local_daily_date if local_daily_date else 'No Data'}")
            ans = input(f"[?] Latest data for <<daily>> tickers from yfinance is available, would you like to update? <y/n>: ").strip().lower()
            if ans == 'y':
                print("[*] Launching Daily Data Fetcher...")
                daily_script = os.path.join(ROOT_DIR, "tools", "data_manager", "scraper_daily.py")
                subprocess.run([sys.executable, daily_script])
        else:
            print(f"    ✔ Local Daily Data is up to date ({local_daily_date}).")

        # --- 2. INTRADAY PROMPT ---
        print("\n--- Intraday Data Status ---")
        if local_intra_date is None or local_intra_date < latest_market_date:
            print(f"    Local Intraday Date: {local_intra_date if local_intra_date else 'No Data'}")
            ans = input(f"[?] Latest data for <<intraday>> tickers from yfinance is available, would you like to update? <y/n>: ").strip().lower()
            if ans == 'y':
                print("[*] Launching Intraday Data Fetcher...")
                intra_script = os.path.join(ROOT_DIR, "tools", "data_manager", "scraper_intraday.py") # Updated
                if os.path.exists(intra_script):
                    subprocess.run([sys.executable, intra_script])
                else:
                    print("    [!] Intraday scraper_intraday.py not found in tools/data_manager/") # Updated
        else:
            print(f"    ✔ Local Intraday Data is up to date ({local_intra_date}).")

    except Exception as e:
        print(f"    [!] Error checking updates: {e}")

def main():
    print("=== WINTRA SYSTEM MANAGER ===")
    create_dirs()
    migrate_files()
    migrate_data_architecture()
    
    check_data_updates()
    print("\n[COMPLETE] Wintra Manager finished execution.")

if __name__ == "__main__":
    main()
