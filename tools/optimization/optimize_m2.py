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
        
    print("[EVENT] Accessing Wintra Data Cache for Model 2 Optimization...")
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

def evaluate_t3_reversion(df, entry_date):
    """
    Calculates T+3 performance for a mean reversion setup.
    Since this is a 'bottom fishing' trade, we use a wider 
    stop loss (-5%) but look for a fast snap-back.
    """
    future_data = df.loc[df.index >= pd.to_datetime(entry_date)].head(4)
    if len(future_data) < 2: return None
        
    entry_price = future_data['Close'].iloc[0]
    t3_data = future_data.iloc[1:]
    
    max_high = t3_data['High'].max()
    min_low = t3_data['Low'].min()
    actual_close = t3_data['Close'].iloc[-1]
    
    stop_limit = -5.0 # Reversion trades need room to 'wiggle' at the bottom
    
    if min_low <= entry_price * (1 + stop_limit/100):
        return stop_limit
    else:
        # Reversion exits are usually at the first sign of strength
        return ((actual_close - entry_price) / entry_price) * 100

def precalculate_indicators(universe_dict):
    """Pre-calculates indicators for Model 2 Logic."""
    print("[EVENT] Pre-calculating Panic Indicators (EMA20, RSI, Vol Avg)...")
    processed_dict = {}
    
    for ticker, df in universe_dict.items():
        if len(df) < 40: continue
        
        df['EMA_20'] = ta.ema(df['Close'], length=20)
        df['RSI'] = ta.rsi(df['Close'], length=14)
        df['Avg_Vol_20'] = df['Volume'].rolling(20).mean().shift(1)
        
        # Calculate Elasticity (Distance from EMA20)
        df['Elasticity'] = ((df['Close'] - df['EMA_20']) / df['EMA_20']) * 100
        
        processed_dict[ticker] = df.dropna()
    return processed_dict

def run_grid_search(universe_dict, start_date, end_date, regime_label):
    print(f"\n🚀 OPTIMIZING MODEL 2: {regime_label} REVERSION SEARCH ({start_date} to {end_date})")
    print("─"*100)
    
    # ⚙️ PARAMETER SPACE FOR THE SNIPER
    stretch_thresholds = [-8.0, -12.0, -15.0, -18.0] # Distance below EMA20
    vol_multipliers = [1.2, 1.5, 2.0]                # Panic volume spike
    rsi_floors = [25, 30, 35]                        # RSI Over-extension
    
    combinations = list(itertools.product(stretch_thresholds, vol_multipliers, rsi_floors))
    total_combs = len(combinations)
    print(f"[EVENT] Testing {total_combs} Capitulation permutations...")
    
    results = []
    start_time = time.time()
    
    for idx, params in enumerate(combinations):
        stretch, v_mult, rsi_f = params
        sys.stdout.write(f"\r[COMPUTING] {idx+1}/{total_combs} | Stretch:<{stretch}% Vol:>{v_mult}x RSI:<{rsi_f}...")
        sys.stdout.flush()
        
        all_returns = []
        
        for ticker, df in universe_dict.items():
            mask = (df.index >= start_date) & (df.index <= end_date)
            test_df = df.loc[mask].copy()
            if test_df.empty: continue
            
            # Logic: We are looking for a 'Panic Day'
            is_stretched = test_df['Elasticity'] <= stretch
            is_panic_vol = test_df['Volume'] > (test_df['Avg_Vol_20'] * v_mult)
            is_oversold = test_df['RSI'] <= rsi_f
            is_down_day = test_df['Close'] < test_df['Open'] # Must be a red 'panic' day
            
            signals = is_stretched & is_panic_vol & is_oversold & is_down_day
            signal_dates = test_df[signals].index
            
            for d in signal_dates:
                ret = evaluate_t3_reversion(df, d)
                if ret is not None: all_returns.append(ret)
                    
        if all_returns:
            win_rate = (len([x for x in all_returns if x > 0]) / len(all_returns)) * 100
            ev = sum(all_returns) / len(all_returns)
            results.append({
                'params': {'stretch': stretch, 'vol': v_mult, 'rsi': rsi_f},
                'signals': len(all_returns), 'win_rate': win_rate, 'ev': ev
            })

    print(f"\n[EVENT] Search Complete in {time.time() - start_time:.2f}s.")
    
    # Priority: EV, then Win Rate
    valid = [r for r in results if r['signals'] >= 5] # M2 signals are rare, floor is lower
    sorted_results = sorted(valid, key=lambda x: x['ev'], reverse=True)
    
    print(f"🏆 TOP CONFIGURATIONS FOR {regime_label}")
    print("─"*100)
    print(f"{'Rank':<5} | {'Stretch':<10} | {'Vol':<8} | {'RSI':<8} | {'Signals':<8} | {'Win Rate':<10} | {'EV'}")
    print("─"*100)
    for i, res in enumerate(sorted_results[:3]):
        p = res['params']
        print(f"#{i+1:<4} | {p['stretch']}%{'':<5} | {p['vol']}x{'':<4} | <{p['rsi']:<6} | {res['signals']:<8} | {res['win_rate']:.2f}%{'':<4} | {res['ev']:+.2f}%")

def main():
    universe_dict, _ = load_cached_data()
    if not universe_dict: return
    
    processed_dict = precalculate_indicators(universe_dict)

    # 1. Sideways Market (Mid 2025) - Often the best for Reversion models
    run_grid_search(processed_dict, "2025-05-01", "2025-08-01", "SIDEWAYS PING-PONG")

    # 2. Bull Market Pullbacks
    run_grid_search(processed_dict, "2025-11-01", "2026-02-01", "BULL PULLBACK")

    # 3. Bear Market Capitulation
    run_grid_search(processed_dict, "2026-03-02", "2026-05-01", "CRASH/BEAR")

if __name__ == "__main__":
    main()
