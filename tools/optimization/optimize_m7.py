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
        
    print(f"{CYAN}[EVENT] Loading 5m data cache for Model 7 Optimization...{RESET}")
    universe_dict = {}
    for filename in os.listdir(CACHE_DIR):
        if not filename.endswith(".csv"): continue
        ticker = filename.split("_")[0]
        filepath = os.path.join(CACHE_DIR, filename)
        try:
            df = pd.read_csv(filepath)
            if df.empty or 'Datetime' not in df.columns: continue
            df['Datetime'] = pd.to_datetime(df['Datetime'])
            
            # --- TIMEZONE PATCH: Shift naive UTC to WIB (UTC+7) ---
            df['Datetime'] = df['Datetime'] + pd.Timedelta(hours=7)
            
            df.set_index('Datetime', inplace=True)
            universe_dict[ticker] = df
        except Exception:
            pass
    print(f"[EVENT] Loaded {len(universe_dict)} tickers for Washout Analysis.")
    return universe_dict

def simulate_washout_trade(day_data, drop_req=2.0, sl_buffer=1.5, target_recovery=1.0):
    """
    Simulates a "Dip & Rip" Washout trade.
    - drop_req: How far below the open it must drop to trigger the BUY (e.g., 2.0%).
    - sl_buffer: How far below the entry price we put our stop loss (e.g., 1.5%).
    - target_recovery: 1.0 means we target a full return to the Open Price.
    """
    if len(day_data) < 20: return None
    
    # 1. Get the Morning Open Price (First 5m candle)
    try:
        open_price = day_data.between_time('09:00', '09:05')['Open'].iloc[0]
    except IndexError:
        return None # No data right at the open
        
    # Calculate exact price levels
    entry_price = open_price * (1 - (drop_req / 100))
    stop_price = entry_price * (1 - (sl_buffer / 100))
    target_price = entry_price + ((open_price - entry_price) * target_recovery)
    
    # 2. Simulate the timeline
    in_trade = False
    
    for _, row in day_data.iterrows():
        if not in_trade:
            # Trigger: Price crashes down to our Entry Level
            if row['Low'] <= entry_price:
                in_trade = True
                # Check for instant death (crashes straight through stop loss in same bar)
                if row['Low'] <= stop_price:
                    return ((stop_price - entry_price) / entry_price) * 100
        else:
            # We are in the trade. Check Exits.
            if row['High'] >= target_price:
                return ((target_price - entry_price) / entry_price) * 100
            if row['Low'] <= stop_price:
                return ((stop_price - entry_price) / entry_price) * 100
                
    # 3. End of Day Exit (If it chopped sideways all day and never hit target or stop)
    if in_trade:
        eod_price = day_data['Close'].iloc[-1]
        return ((eod_price - entry_price) / entry_price) * 100
        
    return None # Trap was never triggered

def find_target_stocks(universe_dict):
    """
    BASELINE DISCOVERY: Finds stocks that naturally 'Dip & Rip' >2.5% frequently.
    """
    print(f"\n{MAGENTA}🩸 DISCOVERING WASHOUT TARGETS (The Best 'Dip & Rip' Stocks){RESET}")
    print("─"*85)
    
    ticker_stats = []
    # Using a standard 2.5% morning crash with a full recovery target
    standard_drop = 2.5 
    
    for ticker, df in universe_dict.items():
        daily_groups = [group for _, group in df.groupby(df.index.date)]
        results = []
        for day_data in daily_groups:
            res = simulate_washout_trade(day_data, drop_req=standard_drop)
            if res is not None: results.append(res)
            
        if results:
            avg_win = sum(results) / len(results)
            win_rate = len([x for x in results if x > 0]) / len(results) * 100
            # We only care about stocks that do this frequently (e.g., > 4 times in 60 days)
            if len(results) >= 4:
                ticker_stats.append({'ticker': ticker, 'wr': win_rate, 'ev': avg_win, 'count': len(results)})
            
    sorted_targets = sorted(ticker_stats, key=lambda x: (x['wr'], x['ev']), reverse=True)
    
    print(f"{'Ticker':<8} | {'Traps Triggered':<16} | {'Win Rate':<10} | {'Avg Return'}")
    print("─"*85)
    for t in sorted_targets[:10]:
        print(f"{t['ticker']:<8} | {t['count']:<16} | {t['wr']:>8.1f}% | {t['ev']:>+8.2f}%")

    # Generate the whitelist: Must win > 55% of the time on morning crashes
    whitelist = [t['ticker'] for t in sorted_targets if t['wr'] >= 55.0]
    print(f"\n[EVENT] Whitelist Generated: {len(whitelist)} tickers approved for Model 7 optimization.")
    return whitelist

def run_grid_search(universe_dict, whitelist):
    print(f"\n{CYAN}⚙️ OPTIMIZING MODEL 7 (FILTERED WASHOUT DEPTH & TARGETS){RESET}")
    print("─"*85)
    
    # Restrict the grid search to only the Whitelisted tickers
    filtered_universe = {k: v for k, v in universe_dict.items() if k in whitelist}
    
    if not filtered_universe:
        print(f"{RED}⚠️ Whitelist is empty. Cannot optimize.{RESET}")
        return

    # ⚙️ M7 PARAMETER SPACE (Now including Day 1 Resilience Filter)
    res_reqs = [0.4, 0.6]               # NEW: Stock must have closed in top X% of range yesterday
    drop_reqs = [2.0, 3.0, 4.0]         # How deep must the crash be to buy?
    stop_buffers = [1.0, 1.5]           # How tight is the stop loss below entry?
    recovery_targets = [0.5, 1.0]       # 0.5 = Halfway back to open, 1.0 = Full open recovery
    
    combinations = list(itertools.product(res_reqs, drop_reqs, stop_buffers, recovery_targets))
    total_combs = len(combinations)
    print(f"[EVENT] Testing {total_combs} Filtered Washout permutations...")
    
    results = []
    start_time = time.time()
    
    for idx, params in enumerate(combinations):
        res_limit, drop, sl, tgt = params
        sys.stdout.write(f"\r[COMPUTING] {idx+1}/{total_combs} | Res:>{res_limit} | Drop: -{drop}% | SL: -{sl}%...")
        sys.stdout.flush()
        
        all_returns = []
        
        for ticker, df in filtered_universe.items():
            daily_groups = [group for _, group in df.groupby(df.index.date)]
            
            for i in range(len(daily_groups) - 1):
                day1 = daily_groups[i]
                day2 = daily_groups[i+1]
                
                if len(day1) < 20: continue
                
                # --- DAY 1 FILTER (RESILIENCE) ---
                d1_h, d1_l, d1_c = day1['High'].max(), day1['Low'].min(), day1['Close'].iloc[-1]
                d1_res = (d1_c - d1_l) / (d1_h - d1_l) if (d1_h - d1_l) > 0 else 0
                
                if d1_res >= res_limit:
                    # --- DAY 2 WASHOUT EXECUTION ---
                    ret = simulate_washout_trade(day2, drop, sl, tgt)
                    if ret is not None: 
                        all_returns.append(ret)
                    
        if all_returns:
            ev = sum(all_returns) / len(all_returns)
            wr = len([x for x in all_returns if x > 0]) / len(all_returns) * 100
            results.append({'params': params, 'ev': ev, 'wr': wr, 'signals': len(all_returns)})

    print(f"\n[EVENT] Optimization Complete in {time.time() - start_time:.2f}s.")
    
    # Filter for signals >= 30 for statistical relevance in filtered setups
    valid = [r for r in results if r['signals'] >= 30]
    sorted_results = sorted(valid, key=lambda x: x['ev'], reverse=True)
    
    print(f"\n🏆 TOP 5 PERFORMING M7 CONFIGURATIONS (FILTERED)")
    print("─"*110)
    print(f"{'Rank':<5} | {'Min Res':<8} | {'Trap Depth':<12} | {'Stop':<8} | {'Target':<8} | {'Signals':<8} | {'Win Rate':<10} | {'EV'}")
    print("─"*110)
    for i, r in enumerate(sorted_results[:5]):
        p = r['params']
        tgt_str = "Full" if p[3] == 1.0 else "Half"
        print(f"#{i+1:<4} | >{p[0]:<7.1f} | Buy at -{p[1]:<4.1f}% | -{p[2]:<6.1f}% | {tgt_str:<8} | {r['signals']:<8} | {r['wr']:>8.1f}% | {r['ev']:>+8.2f}%")

if __name__ == "__main__":
    universe = load_master_ticker()
    if universe:
        whitelist_tickers = find_target_stocks(universe)
        if whitelist_tickers:
            run_grid_search(universe, whitelist_tickers)
        else:
            print("⚠️ No valid target stocks found for Washout strategy.")