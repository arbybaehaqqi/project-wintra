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

CACHE_DIR = "core/data/intraday_cache"

def load_intraday_cache():
    """Loads the 5-minute bar CSVs from the local cache."""
    if not os.path.exists(CACHE_DIR) or not os.listdir(CACHE_DIR):
        print(f"{RED}❌ Cache missing. Run core/data_fetcher.py first.{RESET}")
        return {}
        
    print(f"{CYAN}[EVENT] Loading 5m data cache for IDX80...{RESET}")
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
    print(f"[EVENT] Loaded {len(universe_dict)} tickers for Model 6 Optimization.")
    return universe_dict

def simulate_orb_trade(day2_data, rr_multiplier=1.5):
    """
    Core Model 6 Execution Logic: 15-Minute Opening Range Breakout (ORB).
    Assumes entry at 09:15 if price > High(09:00-09:14).
    """
    if len(day2_data) < 20: return None
    
    # 1. Map the Opening Range (09:00 - 09:14)
    morning_bars = day2_data.between_time('09:00', '09:14')
    if morning_bars.empty: return None
    
    orb_high = morning_bars['High'].max()
    orb_low = morning_bars['Low'].min()
    
    # 2. Setup Trade Parameters
    risk = orb_high - orb_low
    if risk <= 0: return None
    
    target = orb_high + (risk * rr_multiplier)
    stop = orb_low
    entry = orb_high * 1.001 # 0.1% slippage for entry
    
    # 3. Scan the Day (09:15 onwards)
    trading_bars = day2_data.between_time('09:15', '16:00')
    in_trade = False
    
    for _, row in trading_bars.iterrows():
        if not in_trade:
            if row['High'] > orb_high:
                in_trade = True
                # Check for instant stop-out in the same bar
                if row['Low'] < stop: 
                    return ((stop - entry) / entry) * 100 # Exact ORB Risk
        else:
            if row['High'] >= target: 
                return ((target - entry) / entry) * 100
            if row['Low'] <= stop: 
                return ((stop - entry) / entry) * 100 # Exact ORB Risk
            
    # EOD Exit (Option A)
    if in_trade:
        eod_price = trading_bars['Close'].iloc[-1]
        return (eod_price - entry) / entry * 100
        
    return None

def find_target_stocks(universe_dict):
    """
    REVERSE ENGINEERING: Finds which stocks consistently win at the ORB trade.
    """
    print(f"\n{MAGENTA}🔍 DISCOVERING TARGET STOCKS (The 'Perfect' ORB Performers){RESET}")
    print("─"*85)
    
    ticker_stats = []
    for ticker, df in universe_dict.items():
        daily_groups = [group for _, group in df.groupby(df.index.date)]
        results = []
        for i in range(len(daily_groups)):
            res = simulate_orb_trade(daily_groups[i])
            if res is not None: results.append(res)
            
        if results:
            avg_win = sum(results) / len(results)
            win_rate = len([x for x in results if x > 0]) / len(results) * 100
            ticker_stats.append({'ticker': ticker, 'win_rate': win_rate, 'avg_ret': avg_win, 'count': len(results)})
            
    sorted_targets = sorted(ticker_stats, key=lambda x: x['avg_ret'], reverse=True)
    
    print(f"{'Ticker':<8} | {'Signals':<8} | {'Win Rate':<10} | {'Avg EOD Return'}")
    print("─"*85)
    for t in sorted_targets[:10]:
        print(f"{t['ticker']:<8} | {t['count']:<8} | {t['win_rate']:>8.1f}% | {t['avg_ret']:>+8.2f}%")
    return sorted_targets

def run_optimizer(universe_dict):
    """
    Trains the Day 1 Filter (Strength/Resilience) to predict Day 2 ORB winners.
    """
    print(f"\n{CYAN}⚙️ OPTIMIZING MODEL 6 FILTERS (Day 1 Parameters){RESET}")
    print("─"*85)
    
    # PERMUTATION SPACE
    min_itr = [2.0, 3.0, 4.0]        # How much it moved yesterday
    min_res = [0.4, 0.6, 0.75]       # Where it closed yesterday (0.0 - 1.0)
    rr_targets = [1.0, 1.5, 2.0]     # Reward/Risk multipliers
    
    combinations = list(itertools.product(min_itr, min_res, rr_targets))
    results = []
    
    print(f"[EVENT] Testing {len(combinations)} filter combinations...")

    for params in combinations:
        itr_req, res_req, rr = params
        all_returns = []
        
        for ticker, df in universe_dict.items():
            daily_groups = [group for _, group in df.groupby(df.index.date)]
            for i in range(len(daily_groups) - 1):
                d1 = daily_groups[i]
                d2 = daily_groups[i+1]
                
                # Day 1 Metrics
                d1_o, d1_h, d1_l, d1_c = d1['Open'].iloc[0], d1['High'].max(), d1['Low'].min(), d1['Close'].iloc[-1]
                itr = (d1_h - d1_l) / d1_o * 100
                res = (d1_c - d1_l) / (d1_h - d1_l) if (d1_h - d1_l) > 0 else 0
                
                # If Day 1 passes our filter, we simulate Day 2 ORB
                if itr >= itr_req and res >= res_req:
                    ret = simulate_orb_trade(d2, rr)
                    if ret is not None: all_returns.append(ret)
                    
        if all_returns:
            ev = sum(all_returns) / len(all_returns)
            wr = len([x for x in all_returns if x > 0]) / len(all_returns) * 100
            results.append({'params': params, 'ev': ev, 'wr': wr, 'signals': len(all_returns)})

    # Sort results by Expected Value (EV)
    sorted_results = sorted(results, key=lambda x: x['ev'], reverse=True)
    
    print(f"\n🏆 TOP 5 PERFORMING M6 CONFIGURATIONS")
    print("─"*85)
    print(f"{'Rank':<5} | {'ITR':<6} | {'Res':<6} | {'RR':<6} | {'Signals':<8} | {'Win Rate':<10} | {'EV'}")
    print("─"*85)
    for i, r in enumerate(sorted_results[:5]):
        p = r['params']
        print(f"#{i+1:<4} | >{p[0]:<5.1f} | >{p[1]:<5.2f} | {p[2]:<6.1f} | {r['signals']:<8} | {r['wr']:>8.1f}% | {r['ev']:>+8.2f}%")

if __name__ == "__main__":
    universe = load_intraday_cache()
    if universe:
        # Step 1: Discover who our "natural" winners are
        find_target_stocks(universe)
        # Step 2: Optimize the filters to catch them
        run_optimizer(universe)