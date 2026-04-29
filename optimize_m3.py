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
        
    print("[EVENT] Accessing Wintra Data Cache...")
    with open(CACHE_FILE, 'r') as f:
        cache_payload = json.load(f)
        
    ihsg_data = pd.read_json(io.StringIO(cache_payload['ihsg']))
    ihsg_data.index = pd.to_datetime(ihsg_data.index)
    
    universe_dict = {}
    for ticker, df_json in cache_payload['tickers'].items():
        df = pd.read_json(io.StringIO(df_json))
        df.index = pd.to_datetime(df.index)
        universe_dict[ticker] = df
        
    print(f"[EVENT] Successfully loaded {len(universe_dict)} tickers from cache.")
    return universe_dict, ihsg_data

def evaluate_t3_trade(df, entry_date):
    """Calculates T+3 performance for a breakout setup."""
    future_data = df.loc[df.index >= pd.to_datetime(entry_date)].head(4) # Need entry day + 3
    if len(future_data) < 2: 
        return None
        
    entry_price = future_data['Close'].iloc[0]
    t3_data = future_data.iloc[1:] # The next 3 days
    
    max_high = t3_data['High'].max()
    min_low = t3_data['Low'].min()
    actual_close = t3_data['Close'].iloc[-1]
    
    potential_peak = ((max_high - entry_price) / entry_price) * 100
    potential_drop = ((min_low - entry_price) / entry_price) * 100
    standard_perf = ((actual_close - entry_price) / entry_price) * 100
    
    # Breakout Stop Loss is tight: -3.5% (If a breakout fails, it fails fast)
    stop_limit = -3.5
    
    if potential_drop <= stop_limit:
        return stop_limit
    else:
        return (standard_perf + potential_peak) / 2

def precalculate_indicators(universe_dict):
    """Pre-calculates all rolling data to speed up the Grid Search."""
    print("[EVENT] Pre-calculating historical indicators for optimization... This takes a moment.")
    processed_dict = {}
    
    for ticker, df in universe_dict.items():
        if len(df) < 100: continue
        
        # We need the 20-day average volume shifted by 1 (to compare to today)
        df['Avg_Vol_20'] = df['Volume'].rolling(20).mean().shift(1)
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        df['SMA_50'] = ta.sma(df['Close'], length=50) # NEW: For Structural Trend Alignment
        
        # Calculate daily range for Pivot logic
        df['Day_Range'] = df['High'] - df['Low']
        df['Day_Range'] = df['Day_Range'].replace(0, 0.001) # Avoid DivZero
        df['Relative_Pos'] = (df['Close'] - df['Low']) / df['Day_Range']
        
        processed_dict[ticker] = df.dropna()
        
    print("[EVENT] Indicator Pre-calculation Complete.")
    return processed_dict

def run_grid_search(universe_dict, start_date, end_date):
    """
    The Brute-Force Engine. Tests permutations of Model 3 Parameters.
    """
    print("\n🚀 INITIALIZING WINTRA ALGORITHMIC GRID SEARCH (ROUND 2: QUALITY CONTROL)")
    print("─"*85)
    print(f"Target Scenario : BULL MARKET BREAKOUTS ({start_date} to {end_date})")
    
    # ⚙️ THE EXPANDED PARAMETER SPACE
    lookback_periods = [40, 60]             # Narrowed based on Round 1 winners
    vol_multipliers = [2.0, 2.5, 3.0]       # Maintained volume requirement
    pivot_requirements = [0.15, 0.20]       # Top 15% to Top 20%
    max_ema_stretch = [8.0, 12.0, 15.0]     # NEW: Maximum allowed % distance from EMA20
    
    combinations = list(itertools.product(lookback_periods, vol_multipliers, pivot_requirements, max_ema_stretch))
    total_combs = len(combinations)
    print(f"[EVENT] Parameter Space mapped. {total_combs} combinations queued for testing.")
    print("─"*85)
    
    results = []
    start_time = time.time()
    
    for idx, params in enumerate(combinations):
        lookback, vol_mult, pivot_req, max_stretch = params
        
        # Terminal Progress Update
        sys.stdout.write(f"\r[COMPUTING] Test {idx+1}/{total_combs} | Lookback:{lookback} Vol:{vol_mult}x Pivot:{pivot_req} Stretch:<{max_stretch}%...")
        sys.stdout.flush()
        
        all_trade_returns = []
        
        for ticker, df in universe_dict.items():
            mask = (df.index >= start_date) & (df.index <= end_date)
            test_df = df.loc[mask].copy()
            if test_df.empty: continue
            
            # 1. Breakout Logic
            roll_high = df['High'].rolling(lookback).max().shift(1)
            test_roll_high = roll_high.loc[mask]
            is_breakout = test_df['Close'] > test_roll_high
            
            # 2. Volume Logic
            is_vol_climax = test_df['Volume'] > (test_df['Avg_Vol_20'] * vol_mult)
            
            # 3. Pivot Logic
            is_pivot = test_df['Relative_Pos'] >= (1 - pivot_req)
            
            # 4. TREND ALIGNMENT (NEW: Must be in a structural uptrend)
            is_uptrend = (test_df['Close'] > test_df['EMA_20']) & (test_df['EMA_20'] > test_df['SMA_50'])
            
            # 5. EXHAUSTION FILTER (NEW: Cannot be over-extended on breakout day)
            current_stretch = ((test_df['Close'] - test_df['EMA_20']) / test_df['EMA_20']) * 100
            is_not_overextended = current_stretch <= max_stretch
            
            # Combine all Boolean masks to find signal dates
            signals = is_breakout & is_vol_climax & is_pivot & is_uptrend & is_not_overextended
            signal_dates = test_df[signals].index
            
            for d in signal_dates:
                ret = evaluate_t3_trade(df, d) 
                if ret is not None:
                    all_trade_returns.append(ret)
                    
        # Evaluate this combination
        if all_trade_returns:
            total_signals = len(all_trade_returns)
            wins = len([x for x in all_trade_returns if x > 0])
            win_rate = (wins / total_signals) * 100
            ev = sum(all_trade_returns) / total_signals
            
            results.append({
                'params': {'lookback': lookback, 'vol': vol_mult, 'pivot': pivot_req, 'stretch': max_stretch},
                'signals': total_signals,
                'win_rate': win_rate,
                'ev': ev
            })

    exec_time = time.time() - start_time
    print(f"\n\n[EVENT] Grid Search Complete. Execution Time: {exec_time:.2f} seconds.")
    print("─"*85)
    
    valid_results = [r for r in results if r['signals'] >= 10]
    
    if not valid_results:
        print("❌ No parameter combinations produced enough signals (>10) for statistical validity.")
        return
        
    # We will now sort by WIN RATE primarily, but ensure EV is still high
    # Let's find the sweet spot: Win Rate > 40% and highest EV among those
    sorted_results = sorted(valid_results, key=lambda x: (x['win_rate'], x['ev']), reverse=True)
    
    print("🏆 TOP 3 OPTIMIZED CONFIGURATIONS (Prioritizing Win Rate & Quality)")
    print("─"*85)
    print(f"{'Rank':<5} | {'Lookback':<9} | {'Vol':<6} | {'Pivot':<8} | {'Max Stretch':<12} | {'Signals':<8} | {'Win Rate':<10} | {'Expected Value'}")
    print("─"*85)
    
    for i, res in enumerate(sorted_results[:3]):
        p = res['params']
        print(f"#{i+1:<4} | {p['lookback']:<9} | {p['vol']}x{'':<2} | Top {int(p['pivot']*100)}%{'':<1} | < {p['stretch']}%{'':<5} | {res['signals']:<8} | {res['win_rate']:.2f}%{'':<4} | {res['ev']:+.2f}%")

def main():
    universe_dict, _ = load_cached_data()
    if not universe_dict:
        print("❌ Please run the fetch script first.")
        return
        
    processed_dict = precalculate_indicators(universe_dict)
    
    # Test on the Bull Market window
    test_start = "2025-08-01"
    test_end = "2026-02-01"
    
    run_grid_search(processed_dict, test_start, test_end)

if __name__ == "__main__":
    main()
