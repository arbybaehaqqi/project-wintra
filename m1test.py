import os
import json
import io
import pandas as pd
from datetime import datetime, timedelta
from core.models.m1_trend import TrendModel as LegacyM1
from core.models.m1_trend_opt import TrendModel as OptM1

CACHE_FILE = os.path.join("core", "data", "m2_training_cache.json")

def load_data():
    if not os.path.exists(CACHE_FILE): 
        print(f"❌ Error: {CACHE_FILE} not found.")
        return None, None
    with open(CACHE_FILE, 'r') as f:
        cache = json.load(f)
    
    print(f"📂 Loading cache (Updated: {cache.get('metadata', {}).get('last_updated', 'Unknown')})...")
    ihsg = pd.read_json(io.StringIO(cache['ihsg']))
    ihsg.index = pd.to_datetime(ihsg.index)
    universe = {t: pd.read_json(io.StringIO(df)) for t, df in cache['tickers'].items()}
    for t in universe: universe[t].index = pd.to_datetime(universe[t].index)
    return universe, ihsg

def evaluate_perf(df, date_str):
    curr_mask = df.index < pd.to_datetime(date_str)
    price_entry = df.loc[curr_mask]['Close'].iloc[-1]
    future = df.loc[df.index >= pd.to_datetime(date_str)].head(3)
    if future.empty: return 0.0
    ret = ((future['Close'].iloc[-1] - price_entry) / price_entry) * 100
    return max(ret, -3.0) # Standardize stop loss for comparison

def run_comparison(name, start_date, universe, ihsg):
    print(f"\n📊 {name} PERFORMANCE COMPARISON")
    print("─"*85)
    legacy = LegacyM1()
    opt = OptM1()
    
    results = {"Legacy": [], "Optimized": []}
    logs = {"Legacy": [], "Optimized": []}
    
    dates = [(pd.to_datetime(start_date) + timedelta(days=x)).strftime("%Y-%m-%d") for x in range(90)]
    
    for d in dates:
        dt = pd.to_datetime(d)
        if dt not in ihsg.index: continue
        ihsg_morning = ihsg.loc[ihsg.index < dt]['Close']
        
        for t, df in universe.items():
            morning = df.loc[df.index < dt]
            if len(morning) < 60: continue
            
            # Legacy Evaluation
            if legacy.evaluate(morning['Close'], morning['Volume'], ihsg_morning):
                perf = evaluate_perf(df, d)
                results["Legacy"].append(perf)
                logs["Legacy"].append(f"{d} | {t.ljust(5)} | {perf:+.2f}%")
            
            # Optimized Evaluation
            if opt.evaluate(morning['Close'], morning['Volume'], morning['Open'], morning['High'], morning['Low'], ihsg_morning):
                perf = evaluate_perf(df, d)
                results["Optimized"].append(perf)
                logs["Optimized"].append(f"{d} | {t.ljust(5)} | {perf:+.2f}%")

    # Summary Table
    print(f"{'Model':<12} | {'Signals':<8} | {'Win Rate':<12} | {'Expected Value'}")
    print("─"*85)
    for key in ["Legacy", "Optimized"]:
        data = results[key]
        wr = (len([x for x in data if x > 0]) / len(data) * 100) if data else 0
        ev = (sum(data) / len(data)) if data else 0
        print(f"{key.ljust(12)} | {len(data):<8} | {wr:.2f}%{'':<6} | {ev:+.2f}%")
    
    # 🔍 SIGNAL REFERENCE LOG (For debugging divergences)
    print("\n🔍 SIGNAL REFERENCE LOG (First 10 for comparison)")
    print("─"*85)
    print(f"{'Date':<10} | {'Ticker':<6} | {'Legacy':<10} | {'Optimized':<10}")
    
    # Combine logs to see overlaps
    all_dates_tickers = sorted(list(set([x.split('|')[0].strip() + x.split('|')[1].strip() for x in logs["Legacy"] + logs["Optimized"]])))
    
    count = 0
    for entry in all_dates_tickers:
        if count >= 15: break # Show only first 15 for brevity
        date_part = entry[:10]
        ticker_part = entry[10:]
        
        leg_hit = next((x.split('|')[2].strip() for x in logs["Legacy"] if date_part in x and ticker_part in x), "---")
        opt_hit = next((x.split('|')[2].strip() for x in logs["Optimized"] if date_part in x and ticker_part in x), "---")
        
        # Only show if there's a difference
        if leg_hit != opt_hit:
            print(f"{date_part} | {ticker_part.ljust(6)} | {leg_hit:<10} | {opt_hit:<10}")
            count += 1
            
    print("─"*85)

if __name__ == "__main__":
    universe, ihsg = load_data()
    if universe:
        run_comparison("BULL REGIME", "2025-11-01", universe, ihsg)
        run_comparison("BEAR REGIME", "2026-03-02", universe, ihsg)
