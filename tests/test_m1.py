import os
import sys
import pandas as pd

# --- VERSION TRACKING ---
VERSION = "2.2.0-Volatility-Guard"  

# --- DYNAMIC ROOT DETECTION ---
def get_root():
    current = os.path.dirname(os.path.abspath(__file__))
    if current.endswith('tests'):
        return os.path.abspath(os.path.join(current, ".."))
    return current

REPO_ROOT = get_root()
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.models.m1_trend import TrendModel

# --- CONFIGURATION ---
CACHE_DIR = os.path.join(REPO_ROOT, 'core', 'data', 'master_ticker', 'daily')
SIGNAL_DATE = "2026-04-23" 
HOLD_DAYS = 3 

# RISK MANAGEMENT: Reject signals that move more than this % on signal day
MAX_SIGNAL_DAY_MOVE = 15.0 

def run_test():
    print(f"=== WINTRA: SWING ANALYSIS + VOLATILITY GUARD ===")
    print(f"[*] Script Version: {VERSION}")
    print(f"[*] Strategy      : {HOLD_DAYS}-Day Hold | Max Signal Move: {MAX_SIGNAL_DAY_MOVE}%")
    
    if not os.path.exists(CACHE_DIR):
        print(f"[!] Error: Cache directory not found.")
        return

    all_files = [f for f in os.listdir(CACHE_DIR) if f.endswith('_1d.csv')]
    tickers = [f.replace('_1d.csv', '') for f in all_files]
    
    m1_model = TrendModel()
    trade_results = []
    rejected_count = 0

    for ticker in tickers:
        file_path = os.path.join(CACHE_DIR, f"{ticker}_1d.csv")
        try:
            df = pd.read_csv(file_path)
            df['Date_Str'] = pd.to_datetime(df['Datetime']).dt.strftime('%Y-%m-%d')
            
            if m1_model.analyze(df, target_date=SIGNAL_DATE):
                idx = df[df['Date_Str'] == SIGNAL_DATE].index[0]
                sig_day = df.iloc[idx]
                
                # --- VOLATILITY GUARD CALCULATION ---
                # How much did it move on the day it broke out? (High-Low range)
                sig_move = ((sig_day['High'] - sig_day['Low']) / sig_day['Low']) * 100
                
                if sig_move > MAX_SIGNAL_DAY_MOVE:
                    rejected_count += 1
                    continue # Skip this "overheated" stock

                # --- SWING EXECUTION ---
                if idx + HOLD_DAYS < len(df):
                    entry_day = df.iloc[idx + 1]
                    exit_day = df.iloc[idx + HOLD_DAYS]
                    
                    buy_price = entry_day['Open']
                    sell_price = exit_day['Close']
                    pnl = ((sell_price - buy_price) / buy_price) * 100
                    
                    trade_results.append({
                        "ticker": ticker,
                        "buy": buy_price,
                        "sell": sell_price,
                        "pnl": pnl,
                        "sig_move": sig_move
                    })
        except Exception:
            continue

    if trade_results:
        print(f"\n--- FILTERED SWING RESULTS ---")
        header = f"{'Ticker':<7} | {'Sig Move %':<12} | {'Buy (Day+1)':<12} | {'Swing P&L'}"
        print(f"    {header}")
        print(f"    {'-'*60}")
        for res in trade_results:
            sign = "+" if res['pnl'] > 0 else ""
            print(f"    [✔] {res['ticker']:<3} | {res['sig_move']:>10.2f}% | {res['buy']:<12.2f} | {sign}{res['pnl']:>6.2f}%")
    
    print("\n" + "="*70)
    print(f"REJECTED: {rejected_count} tickers were 'Too Hot' (> {MAX_SIGNAL_DAY_MOVE}%)")
    print(f"ACCEPTED: {len(trade_results)} tickers passed the Volatility Guard.")
    print("="*70 + "\n")

if __name__ == "__main__":
    run_test()
