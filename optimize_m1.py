import os
import json
import io
import time
import sys
import itertools
import pandas as pd
import pandas_ta as ta

# Constants for caching
CACHE_DIR = os.path.join("core", "data")
CACHE_FILE = os.path.join(CACHE_DIR, "m2_training_cache.json")

def load_cached_data():
    """Loads market data from the local JSON file."""
    if not os.path.exists(CACHE_FILE):
        return None, None
        
    print("[EVENT] Accessing Wintra Data Cache for Model 1 Review...")
    with open(CACHE_FILE, 'r') as f:
        cache_payload = json.load(f)
        
    ihsg_data = pd.read_json(io.StringIO(cache_payload['ihsg']))
    ihsg_data.index = pd.to_datetime(ihsg_data.index)
    
    universe_dict = {}
    for ticker, df_json in cache_payload['tickers'].items():
        df = pd.read_json(io.StringIO(df_json))
        df.index = pd.to_datetime(df.index)
        universe_dict[ticker] = df
        
    print(f"[EVENT] Successfully loaded {len(universe_dict)} tickers.")
    return universe_dict, ihsg_data

def evaluate_t3_trade(df, entry_date):
    """Calculates T+3 performance with a standard -3.0% stop loss."""
    future_data = df.loc[df.index >= pd.to_datetime(entry_date)].head(4)
    if len(future_data) < 2: return None
        
    entry_price = future_data['Close'].iloc[0]
    t3_data = future_data.iloc[1:]
    
    max_high = t3_data['High'].max()
    min_low = t3_data['Low'].min()
    actual_close = t3_data['Close'].iloc[-1]
    
    stop_limit = -3.0 # Consistent stop loss for Model 1 testing
    
    if min_low <= entry_price * (1 + stop_limit/100):
        return stop_limit
    else:
        # Balanced Return calculation
        return (((actual_close - entry_price) / entry_price) * 100 + ((max_high - entry_price) / entry_price) * 100) / 2

def precalculate_indicators(universe_dict):
    """Pre-calculates indicators to speed up search."""
    print("[EVENT] Pre-calculating Indicators for Wide-Grid Search...")
    processed_dict = {}
    
    for ticker, df in universe_dict.items():
        if len(df) < 60: continue
        df['SMA_50'] = ta.sma(df['Close'], length=50)
        df['Day_Range'] = (df['High'] - df['Low']).replace(0, 0.001)
        df['Relative_Pos'] = (df['Close'] - df['Low']) / df['Day_Range']
        df['Avg_Vol_20'] = df['Volume'].rolling(20).mean().shift(1)
        processed_dict[ticker] = df.dropna()
    return processed_dict

def run_grid_search(universe_dict, start_date, end_date, regime_label):
    print(f"\n🚀 OPTIMIZING MODEL 1: {regime_label} ROUND 3 (LOOSE SEARCH) ({start_date} to {end_date})")
    print("─"*110)
    
    # ⚙️ LOOSER PARAMETER SPACE (Finding the balance)
    fast_emas = [5, 10]
    slow_emas = [20, 30]
    vol_multipliers = [1.2, 1.4, 1.7]        # Loosened (Legacy was 1.25)
    pivot_requirements = [0.4, 0.6, 1.0]     # 1.0 effectively removes the pivot filter
    max_stretch_limits = [8.0, 15.0]         # Loosened (Previous was 5%)
    
    combinations = list(itertools.product(fast_emas, slow_emas, vol_multipliers, pivot_requirements, max_stretch_limits))
    total_combs = len(combinations)
    print(f"[EVENT] Testing {total_combs} permutations...")
    
    results = []
    start_time = time.time()
    
    for idx, params in enumerate(combinations):
        f_ema, s_ema, v_mult, pivot, stretch = params
        sys.stdout.write(f"\r[COMPUTING] {idx+1}/{total_combs} | EMA:{f_ema}/{s_ema} Vol:{v_mult}x Pivot:{pivot} Stretch:<{stretch}%...")
        sys.stdout.flush()
        
        all_returns = []
        
        for ticker, df in universe_dict.items():
            mask = (df.index >= start_date) & (df.index <= end_date)
            test_df = df.loc[mask].copy()
            if test_df.empty: continue
            
            ema_f = ta.ema(df['Close'], length=f_ema)
            ema_s = ta.ema(df['Close'], length=s_ema)
            
            is_stacked = (test_df['Close'] > ema_f.loc[mask]) & (ema_f.loc[mask] > ema_s.loc[mask])
            is_vol = test_df['Volume'] > (test_df['Avg_Vol_20'] * v_mult)
            is_pivot = test_df['Relative_Pos'] >= (1 - pivot)
            
            current_stretch = ((test_df['Close'] - ema_f.loc[mask]) / ema_f.loc[mask]) * 100
            is_not_exhausted = current_stretch <= stretch
            
            # Structural check (SMA50) - Only apply in Bull if it helps
            is_structural = True
            if regime_label == "BULL":
                is_structural = ema_s.loc[mask] > test_df['SMA_50']
            
            signals = is_stacked & is_vol & is_pivot & is_not_exhausted & is_structural
            signal_dates = test_df[signals].index
            
            for d in signal_dates:
                ret = evaluate_t3_trade(df, d)
                if ret is not None: all_returns.append(ret)
                    
        if all_returns:
            win_rate = (len([x for x in all_returns if x > 0]) / len(all_returns)) * 100
            ev = sum(all_returns) / len(all_returns)
            results.append({
                'params': {'f': f_ema, 's': s_ema, 'v': v_mult, 'p': pivot, 'st': stretch},
                'signals': len(all_returns), 'win_rate': win_rate, 'ev': ev
            })

    print(f"\n[EVENT] Search Complete in {time.time() - start_time:.2f}s.")
    
    # Priority: Signals > 150 (for Bull) or > 20 (for Bear), then high EV
    min_signals = 150 if regime_label == "BULL" else 20
    valid = [r for r in results if r['signals'] >= min_signals]
    sorted_results = sorted(valid, key=lambda x: x['ev'], reverse=True)
    
    print(f"🏆 TOP CONFIGURATIONS FOR {regime_label}")
    print("─"*110)
    print(f"{'Rank':<5} | {'EMA (F/S)':<10} | {'Vol':<5} | {'Pivot':<7} | {'Stretch':<8} | {'Signals':<8} | {'Win Rate':<10} | {'EV'}")
    print("─"*110)
    for i, res in enumerate(sorted_results[:3]):
        p = res['params']
        pivot_str = "OFF" if p['p'] == 1.0 else f"Top {int(p['p']*100)}%"
        print(f"#{i+1:<4} | {p['f']}/{p['s']:<6} | {p['v']}x{'':<2} | {pivot_str:<7} | <{p['st']}%{'':<3} | {res['signals']:<8} | {res['win_rate']:.2f}%{'':<4} | {res['ev']:+.2f}%")

def main():
    universe_dict, _ = load_cached_data()
    if not universe_dict: return
    processed_dict = precalculate_indicators(universe_dict)

    # 1. BULL REGIME
    run_grid_search(processed_dict, "2025-11-01", "2026-02-01", "BULL")
    
    # 2. BEAR REGIME
    run_grid_search(processed_dict, "2026-03-02", "2026-05-01", "BEAR")

if __name__ == "__main__":
    main()
