import os
import sys
import json
import pandas as pd
import yfinance as yf
from datetime import datetime

# --- DYNAMIC ROOT DETECTION ---
def get_root():
    current = os.path.dirname(os.path.abspath(__file__))
    if "tools" in current and "data_manager" in current:
        return os.path.abspath(os.path.join(current, "..", ".."))
    return current

ROOT_DIR = get_root()
DAILY_DIR = os.path.join(ROOT_DIR, "core", "data", "master_ticker", "daily")
UNIVERSE_FILE = os.path.join(ROOT_DIR, "core", "data", "idx80_list.json")

def ensure_dir():
    if not os.path.exists(DAILY_DIR):
        os.makedirs(DAILY_DIR)

def load_universe():
    if not os.path.exists(UNIVERSE_FILE):
        print(f"[!] Universe file not found at {UNIVERSE_FILE}")
        return []
    with open(UNIVERSE_FILE, 'r') as f:
        data = json.load(f)
        # Handle list or dict formats
        if isinstance(data, dict) and 'tickers' in data:
            return data['tickers']
        elif isinstance(data, list):
            return data
        return []

def fetch_daily_data():
    print(f"=== WINTRA DAILY DATA FETCHER ===")
    print(f"[*] Lookback: 2 Years | Interval: 1 Day")
    
    ensure_dir()
    tickers = load_universe()
    
    if not tickers:
        print("[!] No tickers loaded. Exiting.")
        return

    success_count = 0
    fail_count = 0

    for ticker in tickers:
        # Format for Indonesian stocks on Yahoo Finance
        yf_ticker = f"{ticker}.JK" if not ticker.endswith(".JK") else ticker
        
        try:
            print(f"    -> Fetching {yf_ticker}...")
            stock = yf.Ticker(yf_ticker)
            df = stock.history(period="2y", interval="1d")
            
            if df.empty:
                print(f"       [!] No data returned for {yf_ticker}")
                fail_count += 1
                continue
                
            # Clean up the dataframe
            df.reset_index(inplace=True)
            # Rename 'Date' to 'Datetime' to match your Wintra engine standard
            if 'Date' in df.columns:
                df.rename(columns={'Date': 'Datetime'}, inplace=True)
                
            # Standardize Datetime format (remove timezone to match intraday)
            if pd.api.types.is_datetime64_any_dtype(df['Datetime']):
                df['Datetime'] = df['Datetime'].dt.tz_localize(None)
                
            # Drop unnecessary columns to perfectly match Intraday OHLCV format
            cols_to_drop = ['Dividends', 'Stock Splits']
            df.drop(columns=[col for col in cols_to_drop if col in df.columns], inplace=True)
            
            # Round price columns to 2 decimal places to clean up adjusted prices
            price_cols = ['Open', 'High', 'Low', 'Close']
            df[price_cols] = df[price_cols].round(2)
                
            # Save to the daily folder
            save_path = os.path.join(DAILY_DIR, f"{ticker}_1d.csv")
            df.to_csv(save_path, index=False)
            success_count += 1
            
        except Exception as e:
            print(f"       [!] Error fetching {yf_ticker}: {e}")
            fail_count += 1

    print("\n=== FETCH COMPLETE ===")
    print(f"✔ Successfully updated: {success_count} tickers")
    print(f"✘ Failed to fetch: {fail_count} tickers")
    print(f"[*] Data saved to: {DAILY_DIR}\n")

if __name__ == "__main__":
    fetch_daily_data()
