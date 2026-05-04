import os
import pandas as pd
from datetime import datetime

# Configuration
CACHE_DIR = "core/data/intraday_cache"

# ANSI Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
GRAY = "\033[90m"
RESET = "\033[0m"

def run_diagnostic():
    print(f"\n{CYAN}🧹 WINTRA INTRADAY CACHE DIAGNOSTIC & CLEANUP{RESET}")
    print(f"{GRAY}Target: Standardizing all 5m bar data...{RESET}\n")

    if not os.path.exists(CACHE_DIR):
        print(f"{RED}❌ Error: Cache directory {CACHE_DIR} not found.{RESET}")
        return

    files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".csv")]
    
    stats = {
        "processed": 0,
        "standardized": 0,
        "deleted_empty": 0,
        "deleted_short": 0,
        "errors": 0
    }

    print(f"{'Ticker':<10} | {'Bars':<8} | {'Days':<6} | {'Status'}")
    print("─"*60)

    for f in files:
        ticker = f.split("_")[0]
        filepath = os.path.join(CACHE_DIR, f)
        stats["processed"] += 1
        
        try:
            # 1. Load Data
            df = pd.read_csv(filepath)
            
            # Check if empty
            if df.empty or len(df) < 5:
                os.remove(filepath)
                print(f"{ticker:<10} | {'0':<8} | {'0':<6} | {RED}🗑️ Deleted (Empty){RESET}")
                stats["deleted_empty"] += 1
                continue

            # 2. Identify and Standardize Time Column (Aggressive Detection)
            # Strategy A: Look for keywords
            time_col = next((c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()), None)
            
            # Strategy B: Common fallback headers from various exports
            if not time_col:
                fallbacks = ['index', 'Unnamed: 0', 'timestamp']
                for fb in fallbacks:
                    if fb in df.columns:
                        time_col = fb
                        break
            
            # Strategy C: Brute Force check the first column content
            if not time_col and len(df.columns) > 0:
                try:
                    # Test if the first column can be parsed as dates (Explicitly using ISO8601 to fix Warning)
                    pd.to_datetime(df.iloc[:, 0].head(5), format='ISO8601')
                    time_col = df.columns[0]
                except:
                    pass

            if time_col:
                if time_col != "Datetime":
                    df.rename(columns={time_col: "Datetime"}, inplace=True)
                    stats["standardized"] += 1
            else:
                # Still no date column found
                print(f"{ticker:<10} | {len(df):<8} | {'?':<6} | {YELLOW}⚠️ No Date Col{RESET}")
                continue

            # 3. Data Integrity Check (Count unique days)
            # Explicitly using ISO8601 for consistent parsing
            df['Datetime'] = pd.to_datetime(df['Datetime'], format='ISO8601')
            unique_days = len(df['Datetime'].dt.date.unique())
            
            # If a file has less than 3 days of data, it's not useful for our D1/D2 models
            if unique_days < 3:
                os.remove(filepath)
                print(f"{ticker:<10} | {len(df):<8} | {unique_days:<6} | {RED}🗑️ Deleted (Too Short){RESET}")
                stats["deleted_short"] += 1
                continue

            # 4. Save Cleaned Version
            # We save it back with the standard 'Datetime' header
            df.to_csv(filepath, index=False)
            print(f"{ticker:<10} | {len(df):<8} | {unique_days:<6} | {GREEN}✅ Healthy{RESET}")

        except Exception as e:
            print(f"{ticker:<10} | {'?':<8} | {'?':<6} | {RED}❌ Error: {str(e)[:20]}{RESET}")
            stats["errors"] += 1

    # Final Summary
    print("\n" + "═"*60)
    print(f"📊 {MAGENTA}CACHE HEALTH SUMMARY{RESET}")
    print("─"*60)
    print(f"Total Tickers Scanned : {stats['processed']}")
    print(f"Standardized Headers  : {stats['standardized']}")
    print(f"Empty Files Purged    : {stats['deleted_empty']}")
    print(f"Short Data Purged     : {stats['deleted_short']}")
    print(f"Remaining Healthy     : {stats['processed'] - stats['deleted_empty'] - stats['deleted_short'] - stats['errors']}")
    print("═"*60 + "\n")

if __name__ == "__main__":
    run_diagnostic()
