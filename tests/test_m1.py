import os
import sys
import pandas as pd
from datetime import datetime

# --- DYNAMIC ROOT DETECTION ---
def get_root():
    current = os.path.dirname(os.path.abspath(__file__))
    # If in 'tests' folder, root is 1 level up
    if current.endswith('tests'):
        return os.path.abspath(os.path.join(current, ".."))
    return current

REPO_ROOT = get_root()
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.models.m1_trend import TrendModel
from core.data_gate import DataGate

# --- CONFIGURATION ---
# M1 is a Trend model, so we point it to the 'daily' subfolder
CACHE_DIR = os.path.join(REPO_ROOT, 'core', 'data', 'master_ticker', 'daily')
TARGET_DATE = '2026-04-27'  # Adjust this to a known bullish date for testing

def run_test():
    print(f"=== TESTING MODEL 1 (TREND) ===")
    print(f"[*] Data Source: {CACHE_DIR}")
    print(f"[*] Target Date: {TARGET_DATE}")
    
    m1_model = TrendModel()
    gate = DataGate()
    
    # Use the gate to get valid tickers from the new 'daily' folder
    tickers = [f.replace('_1d.csv', '') for f in os.listdir(CACHE_DIR) if f.endswith('_1d.csv')]
    
    candidates = []
    print(f"[*] Scanning {len(tickers)} tickers...")

    for ticker in tickers:
        file_path = os.path.join(CACHE_DIR, f"{ticker}_1d.csv")
        try:
            df = pd.read_csv(file_path)
            # Ensure Datetime format is consistent
            df['Datetime'] = pd.to_datetime(df['Datetime']).dt.strftime('%Y-%m-%d')
            
            # Run Model 1 Logic
            is_buy = m1_model.analyze(df, target_date=TARGET_DATE)
            
            if is_buy:
                candidates.append(ticker)
                print(f"    [BUY SIGNAL] {ticker}")
        except Exception as e:
            continue

    print("\n" + "="*30)
    if candidates:
        print(f"RESULTS: Found {len(candidates)} candidates.")
        print(f"TICKERS: {', '.join(candidates)}")
    else:
        print(f"RESULTS: No M1 candidates found for {TARGET_DATE}.")
    print("="*30)

if __name__ == "__main__":
    run_test()
