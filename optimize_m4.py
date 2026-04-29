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
    if not os.path.exists(CACHE_FILE):
        return None, None
        
    print("[EVENT] Accessing Wintra Data Cache for Model 4 Refined Optimization...")
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
    """Calculates T+3 performance with a trailing stop."""
    future_data = df.loc[df.index >= pd.to_datetime(entry_date)].head(4)
    if len(future_data) < 2: return None
        
    entry_price = future_data['Close'].iloc[0]
    t3_data = future_data.iloc[1:]
    
    max_high = t3_data['High'].max()
    min_low = t3_data['Low'].min()
    actual_close = t3_data['Close'].iloc[-1]
    
    # Leaders shouldn't drop much. Tight stop loss at -3.0%
    stop_limit = -3.0 
    
    if min_low <= entry_price * (1 + stop_limit/100):
        return stop_limit
    else:
        return (((actual_close - entry_price) / entry_price) * 100 + ((max_high - entry_price) / entry_price) * 100) / 2

def precalculate_indicators(universe_dict, ihsg_data):
    print("[EVENT] Pre-calculating RS Lines, High Proximity, and Momentum...")
    processed_dict = {}
    
    for ticker, df in universe_dict.items():
        if len(df) < 60: continue
        
        # Align series to ensure accurate division
        temp_df = pd.DataFrame({
            'Open': df['Open'],
            'Close': df['Close'], 
            'IHSG': ihsg_data['Close'], 
            'Volume': df['Volume'],
            'High': df['High'],
            'Low': df['Low']
        }).dropna()
        
        if len(temp_df) < 50: continue
        
        # 1. Base RS Line
        temp_df['RS_Line'] = temp_df['Close'] / temp_df['IHSG']
        
        # 2. Volume Profile
        temp_df['Avg_Vol_20'] = temp_df['Volume'].rolling(20).mean().shift(1)
        
        # 3. High Proximity (Rolling 20-day High)
        temp_df['High_20'] = temp_df['High'].rolling(20).max().shift(1)
        temp_df['Dist_to_High'] = ((temp_df['High_20'] - temp_df['Close']) / temp_df['Close']) * 100
        
        processed_dict[ticker] = temp_df.dropna()
        
    return processed_dict

def run_grid_search(universe_dict, start_date, end_date):
    print(f"\n🚀 MODEL 4 REFINED OPTIMIZATION: EXHAUSTION FILTERING ({start_date} to {end_date})")
    print("─"*125)
    
    # ⚙️ REFINED PARAMETER SPACE
    rs_speeds = [(10, 20), (20, 50)]         # Best pairs from round 1
    vol_reqs = [1.2, 1.5]                    # Best volume multipliers
    high_proximity = [5.0, 8.0]              # Let the stock breathe a bit
    max_stretch_limits = [5.0, 8.0, 12.0]    # NEW: Filter blow-off tops
    green_candles = [True, False]            # NEW: Require strong daily close
    
    combinations = list(itertools.product(rs_speeds, vol_reqs, high_proximity, max_stretch_limits, green_candles))
    total_combs = len(combinations)
    print(f"[EVENT] Testing {total_combs} Refined Alpha permutations...")
    
    results = []
    start_time = time.time()
    
    for idx, params in enumerate(combinations):
        rs_pair, v_mult, prox_lim, stretch_lim, require_green = params
        f_len, s_len = rs_pair
        sys.stdout.write(f"\r[COMPUTING] {idx+1}/{total_combs} | RS:{f_len}/{s_len} Vol:>{v_mult}x Prox:<{prox_lim}% Stretch:<{stretch_lim}% Green:{require_green}...")
        sys.stdout.flush()
        
        all_returns = []
        
        for ticker, df in universe_dict.items():
            rs_fast = ta.ema(df['RS_Line'], length=f_len)
            rs_slow = ta.sma(df['RS_Line'], length=s_len)
            p_fast = ta.ema(df['Close'], length=f_len)
            p_slow = ta.sma(df['Close'], length=s_len)
            
            mask = (df.index >= start_date) & (df.index <= end_date)
            test_df = df.loc[mask]
            if test_df.empty: continue
            
            is_rs_trending = (test_df['RS_Line'] > rs_fast.loc[mask]) & (rs_fast.loc[mask] > rs_slow.loc[mask])
            is_price_trending = (test_df['Close'] > p_fast.loc[mask]) & (p_fast.loc[mask] > p_slow.loc[mask])
            is_vol_confirmed = test_df['Volume'] > (test_df['Avg_Vol_20'] * v_mult)
            is_near_high = test_df['Dist_to_High'] <= prox_lim
            
            # Exhaustion Filter: Don't buy if price is > X% above the fast EMA
            current_stretch = ((test_df['Close'] - p_fast.loc[mask]) / p_fast.loc[mask]) * 100
            is_not_exhausted = current_stretch <= stretch_lim
            
            # Momentum Filter: Must finish higher than the open
            if require_green:
                is_green = test_df['Close'] > test_df['Open']
            else:
                is_green = True
            
            signals = is_rs_trending & is_price_trending & is_vol_confirmed & is_near_high & is_not_exhausted & is_green
            signal_dates = test_df[signals].index
            
            for d in signal_dates:
                ret = evaluate_t3_trade(df, d) 
                if ret is not None: all_returns.append(ret)
                    
        if all_returns:
            win_rate = (len([x for x in all_returns if x > 0]) / len(all_returns)) * 100
            ev = sum(all_returns) / len(all_returns)
            results.append({
                'params': {'rs': f"{f_len}/{s_len}", 'vol': v_mult, 'prox': prox_lim, 'stretch': stretch_lim, 'green': require_green},
                'signals': len(all_returns), 'win_rate': win_rate, 'ev': ev
            })

    print(f"\n[EVENT] Search Complete in {time.time() - start_time:.2f}s.")
    
    valid = [r for r in results if 10 <= r['signals'] <= 150]
    sorted_results = sorted(valid, key=lambda x: (x['win_rate'], x['ev']), reverse=True)
    
    if not sorted_results:
        print("⚠️ No configurations met the criteria. Showing top 3 raw results instead:")
        sorted_results = sorted(results, key=lambda x: x['ev'], reverse=True)

    print(f"🏆 TOP CONFIGURATIONS FOR REFINED ALPHA LEADERSHIP")
    print("─"*125)
    print(f"{'Rank':<5} | {'RS MAs':<10} | {'Vol':<6} | {'Dist to High':<13} | {'Max Stretch':<12} | {'Green Only':<11} | {'Signals':<8} | {'Win Rate':<10} | {'EV'}")
    print("─"*125)
    for i, res in enumerate(sorted_results[:5]):
        p = res['params']
        print(f"#{i+1:<4} | {p['rs']:<10} | >{p['vol']}x | < {p['prox']}%{'':<8} | < {p['stretch']}%{'':<7} | {str(p['green']):<11} | {res['signals']:<8} | {res['win_rate']:.2f}%{'':<4} | {res['ev']:+.2f}%")

def main():
    universe_dict, ihsg_data = load_cached_data()
    if not universe_dict: return
    
    processed_dict = precalculate_indicators(universe_dict, ihsg_data)

    # Optimize strictly during the Bull regime where Leadership models thrive
    run_grid_search(processed_dict, "2025-11-01", "2026-02-01")

if __name__ == "__main__":
    main()
