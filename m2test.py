import os
import json
import io
import pandas as pd
from datetime import datetime, timedelta
from core.models.m2_revert import RevertModel as LegacyM2
from core.models.m2_revert_opt import RevertModel as OptM2

CACHE_FILE = os.path.join("core", "data", "m2_training_cache.json")

def load_data():
    if not os.path.exists(CACHE_FILE): 
        print(f"❌ Error: {CACHE_FILE} not found. Run training script first.")
        return None, None
    with open(CACHE_FILE, 'r') as f:
        cache = json.load(f)
    
    print(f"📂 Loading Wintra Cache (Last Updated: {cache.get('metadata', {}).get('last_updated', 'Unknown')})...")
    ihsg = pd.read_json(io.StringIO(cache['ihsg']))
    ihsg.index = pd.to_datetime(ihsg.index)
    universe = {t: pd.read_json(io.StringIO(df)) for t, df in cache['tickers'].items()}
    for t in universe: universe[t].index = pd.to_datetime(universe[t].index)
    return universe, ihsg

def evaluate_perf(df, date_str):
    """T+3 Return Calculation with -5% Stop Loss."""
    curr_mask = df.index < pd.to_datetime(date_str)
    price_entry = df.loc[curr_mask]['Close'].iloc[-1]
    future = df.loc[df.index >= pd.to_datetime(date_str)].head(4) 
    if len(future) < 2: return 0.0
    
    t3_data = future.iloc[1:]
    actual_close = t3_data['Close'].iloc[-1]
    min_low = t3_data['Low'].min()
    
    # Standard -5% Stop Loss for Reversion
    if min_low <= price_entry * 0.95:
        return -5.0
    
    return ((actual_close - price_entry) / price_entry) * 100

def run_comparison(name, start_date, universe, ihsg):
    print(f"\n📊 {name} M2 PERFORMANCE COMPARISON")
    print("─"*85)
    legacy = LegacyM2()
    opt = OptM2()
    
    results = {"Legacy": [], "Optimized": []}
    
    dates = [(pd.to_datetime(start_date) + timedelta(days=x)).strftime("%Y-%m-%d") for x in range(90)]
    
    for d in dates:
        dt = pd.to_datetime(d)
        if dt not in ihsg.index: continue
        ihsg_morning = ihsg.loc[ihsg.index < dt]['Close']
        
        for t, df in universe.items():
            morning = df.loc[df.index < dt]
            if len(morning) < 40: continue
            
            # Legacy Eval
            if legacy.evaluate(morning['Close'], morning['Volume'], morning['Open'], morning['Low'], morning['High'], ihsg_morning):
                results["Legacy"].append(evaluate_perf(df, d))
            
            # Optimized Eval
            if opt.evaluate(morning['Close'], morning['Volume'], morning['Open'], morning['High'], morning['Low'], ihsg_morning):
                results["Optimized"].append(evaluate_perf(df, d))

    print(f"{'Model':<12} | {'Signals':<8} | {'Win Rate':<12} | {'Expected Value'}")
    print("─"*85)
    for key in ["Legacy", "Optimized"]:
        data = results[key]
        wr = (len([x for x in data if x > 0]) / len(data) * 100) if data else 0
        ev = (sum(data) / len(data)) if data else 0
        print(f"{key.ljust(12)} | {len(data):<8} | {wr:.2f}%{'':<6} | {ev:+.2f}%")

if __name__ == "__main__":
    universe, ihsg = load_data()
    if universe:
        run_comparison("SIDEWAYS PING-PONG", "2025-05-01", universe, ihsg)
        run_comparison("BULL PULLBACKS", "2025-11-01", universe, ihsg)
        run_comparison("CRASH/BEAR", "2026-03-02", universe, ihsg)
