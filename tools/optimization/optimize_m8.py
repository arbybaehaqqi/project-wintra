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
RESET = "\033[0m"

CACHE_DIR = "core/data/master_ticker"

def load_master_ticker():
    if not os.path.exists(CACHE_DIR) or not os.listdir(CACHE_DIR):
        print(f"{RED}❌ Cache missing. Run core/data_fetcher.py first.{RESET}")
        return {}
        
    print(f"{CYAN}[EVENT] Loading 5m data cache for Model 8 (Camarilla)...{RESET}")
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
    print(f"[EVENT] Loaded {len(universe_dict)} tickers for Ping-Pong Analysis.")
    return universe_dict

def simulate_camarilla_trade(day1, day2, target_multiplier):
    """
    Calculates Camarilla S3/S4 from Day 1 and simulates buying the S3 bounce on Day 2.
    """
    if len(day1) < 10 or len(day2) < 20: return None
    
    # 1. Day 1 Camarilla Math
    y_h = day1['High'].max()
    y_l = day1['Low'].min()
    y_c = day1['Close'].iloc[-1]
    y_range = y_h - y_l
    
    if y_range == 0: return None

    # Standard Camarilla Formulas
    s3 = y_c - (y_range * 1.1 / 4)
    s4 = y_c - (y_range * 1.1 / 2)
    r3 = y_c + (y_range * 1.1 / 4)
    
    # GAP DOWN PROTECTION: If the stock opens below S3, the floor is broken. Abort.
    if day2['Open'].iloc[0] < s3:
        return None
    
    # 2. Trade Parameters
    entry_price = s3 
    stop_price = s4
    
    # Target is now a standardized Risk/Reward multiplier of the S3-S4 box
    risk = entry_price - stop_price
    target_price = entry_price + (risk * target_multiplier)
    
    # 3. Simulate Day 2
    in_trade = False
    
    for _, row in day2.iterrows():
        if not in_trade:
            # Trigger: Price hits the S3 Floor limit order
            if row['Low'] <= entry_price:
                in_trade = True
                # Check instant stop-out in the same bar
                if row['Low'] <= stop_price:
                    return ((stop_price - entry_price) / entry_price) * 100
        else:
            # Check Exits
            if row['High'] >= target_price:
                return ((target_price - entry_price) / entry_price) * 100
            if row['Low'] <= stop_price:
                return ((stop_price - entry_price) / entry_price) * 100
                
    # EOD Exit
    if in_trade:
        eod_price = day2['Close'].iloc[-1]
        return ((eod_price - entry_price) / entry_price) * 100
        
    return None

def find_target_stocks(universe_dict):
    print(f"\n{MAGENTA}🏓 DISCOVERING CAMARILLA TARGETS (The Best Range-Bound Stocks){RESET}")
    print("─"*85)
    
    ticker_stats = []
    
    for ticker, df in universe_dict.items():
        daily_groups = [group for _, group in df.groupby(df.index.date)]
        results = []
        for i in range(len(daily_groups) - 1):
            res = simulate_camarilla_trade(daily_groups[i], daily_groups[i+1], target_multiplier=1.0)
            if res is not None: results.append(res)
            
        if results and len(results) >= 5:
            avg_win = sum(results) / len(results)
            win_rate = len([x for x in results if x > 0]) / len(results) * 100
            ticker_stats.append({'ticker': ticker, 'wr': win_rate, 'ev': avg_win, 'count': len(results)})
            
    sorted_targets = sorted(ticker_stats, key=lambda x: x['wr'], reverse=True)
    whitelist = [t['ticker'] for t in sorted_targets if t['wr'] >= 55.0]
    
    print(f"{'Ticker':<8} | {'S3 Bounces':<12} | {'Win Rate':<10} | {'Avg Return'}")
    print("─"*85)
    for t in sorted_targets[:10]:
        print(f"{t['ticker']:<8} | {t['count']:<12} | {t['wr']:>8.1f}% | {t['ev']:>+8.2f}%")
        
    print(f"\n[EVENT] Whitelist Generated: {len(whitelist)} tickers approved for Model 8 optimization.")
    return whitelist

def run_grid_search(universe_dict, whitelist):
    print(f"\n{CYAN}⚙️ OPTIMIZING MODEL 8 (CAMARILLA PING-PONG){RESET}")
    print("─"*85)
    
    filtered_universe = {k: v for k, v in universe_dict.items() if k in whitelist}
    
    # ⚙️ M8 PARAMETER SPACE
    min_itr_reqs = [3.0, 4.0, 5.0]
    max_res_reqs = [0.4, 0.6]  
    target_mults = [1.0, 1.5]  # RR multipliers: 1.0x Risk, 1.5x Risk
    
    combinations = list(itertools.product(min_itr_reqs, max_res_reqs, target_mults))
    total_combs = len(combinations)
    print(f"[EVENT] Testing {total_combs} Range permutations...")
    
    results = []
    
    for idx, params in enumerate(combinations):
        req_itr, max_res, tgt_mult = params
        sys.stdout.write(f"\r[COMPUTING] {idx+1}/{total_combs} | ITR:>{req_itr}% Res:<{max_res} Target:{tgt_mult}x...")
        sys.stdout.flush()
        
        all_returns = []
        
        for ticker, df in filtered_universe.items():
            daily_groups = [group for _, group in df.groupby(df.index.date)]
            for i in range(len(daily_groups) - 1):
                d1 = daily_groups[i]
                d2 = daily_groups[i+1]
                if len(d1) < 10 or len(d2) < 10: continue
                
                d1_o, d1_h, d1_l, d1_c = d1['Open'].iloc[0], d1['High'].max(), d1['Low'].min(), d1['Close'].iloc[-1]
                itr = (d1_h - d1_l) / d1_o * 100
                res = (d1_c - d1_l) / (d1_h - d1_l) if (d1_h - d1_l) > 0 else 0
                
                # Setup: High Volatility yesterday, but a "Doji" or middle close
                if itr >= req_itr and res <= max_res:
                    ret = simulate_camarilla_trade(d1, d2, tgt_mult)
                    if ret is not None: all_returns.append(ret)
                    
        if all_returns:
            ev = sum(all_returns) / len(all_returns)
            wr = len([x for x in all_returns if x > 0]) / len(all_returns) * 100
            results.append({'params': params, 'ev': ev, 'wr': wr, 'signals': len(all_returns)})

    print("\n")
    valid = [r for r in results if r['signals'] >= 10]
    sorted_results = sorted(valid, key=lambda x: x['ev'], reverse=True)
    
    print(f"🏆 TOP 5 PERFORMING M8 CONFIGURATIONS")
    print("─"*85)
    print(f"{'Rank':<5} | {'Min ITR':<8} | {'Max Res':<8} | {'Target':<10} | {'Signals':<8} | {'Win Rate':<10} | {'EV'}")
    print("─"*85)
    for i, r in enumerate(sorted_results[:5]):
        p = r['params']
        print(f"#{i+1:<4} | >{p[0]:<6.1f} | <{p[1]:<6.2f} | {p[2]}x Risk{'':<3} | {r['signals']:<8} | {r['wr']:>8.1f}% | {r['ev']:>+8.2f}%")

if __name__ == "__main__":
    universe = load_master_ticker()
    if universe:
        whitelist = find_target_stocks(universe)
        if whitelist:
            run_grid_search(universe, whitelist)