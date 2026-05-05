import os
import time
import sys
import itertools
import pandas as pd
import numpy as np

# ANSI Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
GRAY = "\033[90m"
RESET = "\033[0m"

CACHE_DIR = "core/data/master_ticker"

def load_master_ticker():
    if not os.path.exists(CACHE_DIR) or not os.listdir(CACHE_DIR):
        print(f"{RED}❌ Cache missing. Run core/data_fetcher.py first.{RESET}")
        return {}
        
    print(f"{CYAN}[EVENT] Loading 5m data cache for Model 5 (Defensive)...{RESET}")
    universe_dict = {}
    for filename in os.listdir(CACHE_DIR):
        if not filename.endswith(".csv"): continue
        ticker = filename.split("_")[0]
        filepath = os.path.join(CACHE_DIR, filename)
        try:
            df = pd.read_csv(filepath)
            if df.empty or 'Datetime' not in df.columns: continue
            df['Datetime'] = pd.to_datetime(df['Datetime'])
            df['Datetime'] = df['Datetime'] + pd.Timedelta(hours=7) # WIB Patch
            df.set_index('Datetime', inplace=True)
            universe_dict[ticker] = df
        except Exception:
            pass
    print(f"[EVENT] Loaded {len(universe_dict)} tickers for Trap Analysis.")
    return universe_dict

def evaluate_trap_performance(day_data):
    """
    Evaluates what happens if you bought a stock at 09:30 WIB after it formed a Trap.
    We are looking for NEGATIVE returns to prove the trap is deadly.
    """
    if len(day_data) < 20: return None
    
    # Isolate the first 30 minutes (09:00 - 09:29)
    morning_bars = day_data.between_time('09:00', '09:29')
    if morning_bars.empty: return None
    
    # Trap Metrics
    m_open = morning_bars['Open'].iloc[0]
    m_high = morning_bars['High'].max()
    m_low = morning_bars['Low'].min()
    m_close = morning_bars['Close'].iloc[-1]
    m_vol = morning_bars['Volume'].sum()
    
    m_range = m_high - m_low
    if m_range == 0: return None
    
    upper_wick = m_high - max(m_open, m_close)
    wick_ratio = upper_wick / m_range
    
    is_red = m_close < m_open
    
    # Fast forward to 15:50 (End of Day)
    eod_price = day_data['Close'].iloc[-1]
    
    # Calculate the return from 09:30 to EOD
    eod_return = ((eod_price - m_close) / m_close) * 100
    
    return {
        'wick_ratio': wick_ratio,
        'is_red': is_red,
        'morning_vol': m_vol,
        'eod_return': eod_return
    }

def run_grid_search(universe_dict):
    print(f"\n{CYAN}⚙️ OPTIMIZING MODEL 5 (MORNING TRAP DETECTOR){RESET}")
    print(f"{GRAY}Goal: Find the parameters that cause the WORST losses (Negative EV){RESET}")
    print("─"*85)
    
    # ⚙️ M5 PARAMETER SPACE (Hunting Toxic Behavior)
    min_wick_ratios = [0.4, 0.5, 0.6]      # Upper wick must be > X% of the 30-min candle
    require_red_candle = [True, False]     # Must the 30-min candle be red?
    
    combinations = list(itertools.product(min_wick_ratios, require_red_candle))
    total_combs = len(combinations)
    print(f"[EVENT] Testing {total_combs} Trap permutations...")
    
    results = []
    
    for idx, params in enumerate(combinations):
        min_wick, req_red = params
        sys.stdout.write(f"\r[COMPUTING] {idx+1}/{total_combs} | Wick > {min_wick*100}% | Red Only: {req_red}...")
        sys.stdout.flush()
        
        trap_returns = []
        
        for ticker, df in universe_dict.items():
            daily_groups = [group for _, group in df.groupby(df.index.date)]
            for day_data in daily_groups:
                res = evaluate_trap_performance(day_data)
                if res is None: continue
                
                # Check if it triggered our "Trap" definition
                is_trap = res['wick_ratio'] >= min_wick
                if req_red and not res['is_red']: is_trap = False
                
                if is_trap:
                    trap_returns.append(res['eod_return'])
                    
        if trap_returns:
            # We want a HIGH percentage of losses (which we'll call "Trap Accuracy")
            losses = [x for x in trap_returns if x < 0]
            trap_accuracy = (len(losses) / len(trap_returns)) * 100
            avg_bleed = sum(trap_returns) / len(trap_returns)
            
            results.append({
                'params': params,
                'signals': len(trap_returns),
                'accuracy': trap_accuracy,  # Higher is better (more reliable trap)
                'avg_bleed': avg_bleed      # More negative is better (deadlier trap)
            })

    print("\n")
    valid = [r for r in results if r['signals'] >= 50]
    # Sort by Most Negative EV (Deadliest Trap)
    sorted_results = sorted(valid, key=lambda x: x['avg_bleed'])
    
    print(f"🚨 TOP 5 DEADLIEST MORNING TRAPS (Avoid These Setups)")
    print("─"*85)
    print(f"{'Rank':<5} | {'Min Wick %':<12} | {'Red Candle':<12} | {'Trap Count':<10} | {'Trap Hit %':<12} | {'Avg Bleed'}")
    print("─"*85)
    for i, r in enumerate(sorted_results[:5]):
        p = r['params']
        print(f"#{i+1:<4} | > {int(p[0]*100)}%{'':<7} | {str(p[1]):<12} | {r['signals']:<10} | {r['accuracy']:>8.1f}%   | {RED}{r['avg_bleed']:>+8.2f}%{RESET}")

if __name__ == "__main__":
    universe = load_master_ticker()
    if universe:
        run_grid_search(universe)