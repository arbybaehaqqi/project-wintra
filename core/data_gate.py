import os
import pandas as pd
import subprocess
import sys
from datetime import datetime, time, timedelta
import pytz

# ANSI Colors (Windows Compatible)
CYAN, GREEN, YELLOW, RED, GRAY, RESET = "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[90m", "\033[0m"

class DataGate:
    """
    Wintra Data Validation Gate V2.1
    Implements 'Lazy Sync' logic: Only fetches from yfinance if local cache is stale.
    Optimized: Gate 2 (Daily) now targets the last completed session to prevent 
    aggressive re-syncing during market hours.
    """
    CACHE_DIR = "core/data/intraday_cache"
    
    @staticmethod
    def _get_wib_now():
        return datetime.now(pytz.timezone('Asia/Jakarta'))

    @staticmethod
    def _is_market_open(now_wib):
        """Checks if current time is within IDX trading hours (approx 09:00 - 16:00)."""
        # Weekends
        if now_wib.weekday() >= 5:
            return False
        # Hours
        current_time = now_wib.time()
        return time(9, 0) <= current_time <= time(16, 15)

    @staticmethod
    def sync_data():
        """Triggers the global scraper to pull latest yfinance data."""
        print(f"{GRAY}[GATE] Cache stale. Synchronizing with yfinance...{RESET}")
        try:
            # Run scraper.py as a subprocess
            result = subprocess.run([sys.executable, "scraper.py"], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"{RED}[ERROR] Scraper failed: {result.stderr}{RESET}")
                return False
            return True
        except Exception as e:
            print(f"{RED}[ERROR] Failed to trigger scraper: {e}{RESET}")
            return False

    @classmethod
    def verify(cls, mode="intraday", force_sync=False):
        """
        Main entry point for the gate.
        force_sync=False: Enables 'Smart Check' (Check Cache -> Fetch if needed).
        """
        now_wib = cls._get_wib_now()
        now_naive = now_wib.replace(tzinfo=None)
        print(f"\n{CYAN}[WINTRA DATA GATE: {mode.upper()} MODE]{RESET}")

        # 1. INITIAL CACHE CHECK (Before Sync)
        is_stale = True
        sample_file = os.path.join(cls.CACHE_DIR, "BBCA_5m.csv")
        
        if os.path.exists(sample_file):
            try:
                # Read only the last row for speed
                df_last = pd.read_csv(sample_file).tail(1)
                latest_data_time = pd.to_datetime(df_last['Datetime'].iloc[0]).replace(tzinfo=None)
                
                if mode == "intraday":
                    # Intraday Check: Stale if more than 35 mins old AND market is currently open
                    diff_mins = (now_naive - latest_data_time).total_seconds() / 60
                    if diff_mins <= 35:
                        is_stale = False
                    elif not cls._is_market_open(now_wib) and latest_data_time.date() == now_naive.date():
                        # Market is closed but we have today's final data
                        is_stale = False

                elif mode == "daily":
                    # Daily Check: We only need the last completed trading day (T-1)
                    # If it's Tuesday 2:00 PM, we only strictly need Monday's data for swing tests.
                    # This prevents constant syncing during the day.
                    
                    # Target is Yesterday
                    target_date = (now_naive - timedelta(days=1)).date()
                    
                    # If it's Monday, target is Friday
                    if now_wib.weekday() == 0: # Monday
                        target_date = (now_naive - timedelta(days=3)).date()
                    
                    # Special Case: If it's late night (after 6 PM), we should expect TODAY'S data
                    if now_wib.time() > time(18, 0):
                        target_date = now_naive.date()

                    if latest_data_time.date() >= target_date:
                        is_stale = False
            except Exception:
                is_stale = True

        # 2. TRIGGER SYNC ONLY IF STALE
        if is_stale or force_sync:
            if not cls.sync_data():
                # If it failed but we have *some* data, let it pass as a warning 
                # (unless force_sync was requested)
                if os.path.exists(sample_file) and not force_sync:
                    print(f"{YELLOW}[WARN] Sync failed, proceeding with existing cache.{RESET}")
                    return True
                else:
                    print(f"{RED}[STOP] GATE CLOSED: Sync failed and no valid cache found.{RESET}")
                    sys.exit(1)
        else:
            print(f"{GREEN}[OK] GATE OPEN: Cache is already fresh. Skipping Sync.{RESET}")

        # 3. FINAL INTEGRITY VERIFICATION
        if not os.path.exists(sample_file):
            print(f"{RED}[STOP] GATE CLOSED: Cache is empty after sync attempt.{RESET}")
            sys.exit(1)
        
        return True