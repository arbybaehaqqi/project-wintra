import os
import pandas as pd
from datetime import datetime
import time

# --- CONFIGURATION ---
CACHE_DIR = "core/data/master_ticker"
REQUIRED_COLUMNS = ["Datetime", "Open", "High", "Low", "Close", "Volume"]

# ANSI Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
GRAY = "\033[90m"
RESET = "\033[0m"

def run_diagnostic():
    print(f"\n{CYAN}📊 WINTRA INTRADAY DATABASE DIAGNOSTIC (DB-XRAY){RESET}")
    print(f"{GRAY}Path: {CACHE_DIR}{RESET}")
    print("═" * 105)

    if not os.path.exists(CACHE_DIR):
        print(f"{RED}❌ CRITICAL: Cache directory not found.{RESET}")
        return

    files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".csv")]
    stats = {"total_tickers": len(files), "valid_format": 0, "total_bars": 0, "oldest_data": None, "newest_data": None}

    print(f"{'Ticker':<8} | {'Bars':<6} | {'Format':<10} | {'Start (WIB)':<18} | {'End (WIB)':<18} | {'Update'}")
    print("─" * 105)

    for f in files:
        ticker = f.split("_")[0]
        filepath = os.path.join(CACHE_DIR, f)
        
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%m-%d %H:%M")
            df = pd.read_csv(filepath)
            bar_count = len(df)
            stats["total_bars"] += bar_count
            
            # --- ADVANCED FORMAT CHECK ---
            headers = list(df.columns)
            time_col = "Datetime" if "Datetime" in headers else None
            
            # Fallback for unnamed index columns (Common in yfinance direct to_csv)
            if not time_col:
                potential_time_cols = [c for c in headers if "Unnamed" in c or "Date" in c or "time" in c.lower()]
                if potential_time_cols:
                    time_col = potential_time_cols[0]
            
            missing = [col for col in REQUIRED_COLUMNS if col not in headers and col != "Datetime"]
            
            if not missing and time_col:
                format_status = f"{GREEN}VALID{RESET}" if "Datetime" in headers else f"{YELLOW}LEGACY{RESET}"
                stats["valid_format"] += 1
            else:
                format_status = f"{RED}MISSING{RESET}"
            
            # --- RANGE CHECKER ---
            if time_col:
                df[time_col] = pd.to_datetime(df[time_col])
                start_dt, end_dt = df[time_col].min(), df[time_col].max()
                
                if stats["oldest_data"] is None or start_dt < stats["oldest_data"]: stats["oldest_data"] = start_dt
                if stats["newest_data"] is None or end_dt > stats["newest_data"]: stats["newest_data"] = end_dt
                
                start_str, end_str = start_dt.strftime("%y-%m-%d %H:%M"), end_dt.strftime("%y-%m-%d %H:%M")
            else:
                start_str, end_str = "N/A", "N/A"

            print(f"{ticker:<8} | {bar_count:<6} | {format_status:<19} | {start_str:<18} | {end_str:<18} | {mtime}")

        except Exception as e:
            print(f"{ticker:<8} | {RED}FAILED{RESET} | Error: {str(e)[:30]}...")

    print("═" * 105)
    print(f"{MAGENTA}🏁 SYSTEM SUMMARY{RESET}")
    health_pct = (stats["valid_format"] / stats["total_tickers"] * 100) if stats["total_tickers"] > 0 else 0
    print(f"Tickers: {YELLOW}{stats['total_tickers']}{RESET} | Integrity: {GREEN if health_pct > 90 else YELLOW}{health_pct:.1f}%{RESET} | Bars: {YELLOW}{stats['total_bars']:,}{RESET}")
    if stats["oldest_data"]:
        print(f"Range  : {GRAY}{stats['oldest_data']} {RESET}to{CYAN} {stats['newest_data']}{RESET}")
    print("═" * 105 + "\n")

if __name__ == "__main__":
    run_diagnostic()