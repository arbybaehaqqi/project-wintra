import os
import json
import io
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from datetime import datetime, timedelta
from core.models.m1_trend import TrendModel
from core.models.m2_revert import RevertModel

# Constants for caching
CACHE_DIR = os.path.join("core", "data")
CACHE_FILE = os.path.join(CACHE_DIR, "m2_training_cache.json")

def load_cached_data():
    """Loads market data from the local JSON file."""
    if not os.path.exists(CACHE_FILE):
        return None, None
        
    with open(CACHE_FILE, 'r') as f:
        cache_payload = json.load(f)
        
    if cache_payload.get('metadata', {}).get('start_date') != "2025-01-01":
        print("⚠️ Cache is too new. Need data from 2025-01-01 for full comparison.")
        return None, None

    print(f"📂 Loading data from local cache...")
    ihsg_data = pd.read_json(io.StringIO(cache_payload['ihsg']))
    ihsg_data.index = pd.to_datetime(ihsg_data.index)
    
    universe_dict = {}
    for ticker, df_json in cache_payload['tickers'].items():
        df = pd.read_json(io.StringIO(df_json))
        df.index = pd.to_datetime(df.index)
        universe_dict[ticker] = df
        
    return universe_dict, ihsg_data

def evaluate_performance(df, date_str, current_regime):
    """Calculates T+3 performance with regime-based stop loss."""
    price_last_close = df.loc[df.index < pd.to_datetime(date_str)]['Close'].iloc[-1]
    future_data = df.loc[df.index >= pd.to_datetime(date_str)].head(3)
    
    if future_data.empty:
        return 0.0
        
    max_high = future_data['High'].max()
    min_low = future_data['Low'].min()
    actual_close = future_data['Close'].iloc[-1]
    
    potential_peak = ((max_high - price_last_close) / price_last_close) * 100
    potential_drop = ((min_low - price_last_close) / price_last_close) * 100
    standard_perf = ((actual_close - price_last_close) / price_last_close) * 100
    
    # Unified Stop Loss logic for comparison
    stop_limit = -3.0 if current_regime != "BEAR" else -5.0
    
    if potential_drop <= stop_limit:
        return stop_limit
    else:
        return (standard_perf + potential_peak) / 2

def simulate_day(date_str, universe_data, ihsg_data, m1, m2):
    """Evaluates both models for a specific day."""
    m1_results = []
    m2_results = []

    ihsg_morning = None
    if not ihsg_data.empty:
        ihsg_mask = ihsg_data.index < pd.to_datetime(date_str)
        ihsg_morning = ihsg_data.loc[ihsg_mask]['Close']

    current_regime = m1.detect_regime(ihsg_morning)

    for ticker, df in universe_data.items():
        morning_mask = df.index < pd.to_datetime(date_str)
        morning_data = df.loc[morning_mask]
        
        if len(morning_data) < 30: continue
        
        # M1 Evaluation (Trend)
        if m1.evaluate(morning_data['Close'], morning_data['Volume'], ihsg_morning):
            m1_results.append(evaluate_performance(df, date_str, current_regime))
                
        # M2 Evaluation (Revert)
        if m2.evaluate(
            morning_data['Close'], 
            morning_data['Volume'], 
            morning_data.get('Open'),
            morning_data.get('Low'),
            morning_data.get('High'),
            ihsg_morning
        ):
            m2_results.append(evaluate_performance(df, date_str, current_regime))
                
    return m1_results, m2_results, current_regime

def run_comparative_scenario(name, start_date_str, universe_dict, ihsg_data):
    print(f"\n📊 COMPARISON: {name}")
    print("─"*75)
    
    m1 = TrendModel()
    m2 = RevertModel()
    
    start_sim = datetime.strptime(start_date_str, "%Y-%m-%d")
    test_dates = [(start_sim + timedelta(days=x)).strftime("%Y-%m-%d") for x in range(90)]
    
    stats = {"M1": [], "M2": [], "Combined": []}
    regimes = set()
    
    for d in test_dates:
        day_dt = pd.to_datetime(d)
        if ihsg_data.empty or day_dt not in ihsg_data.index: continue
        # Cap logic per model to allow fair comparison
        if len(stats["M1"]) >= 200 and len(stats["M2"]) >= 100: break 

        m1_day, m2_day, regime = simulate_day(d, universe_dict, ihsg_data, m1, m2)
        regimes.add(regime)
        stats["M1"].extend(m1_day)
        stats["M2"].extend(m2_day)
        stats["Combined"].extend(m1_day + m2_day)

    # Output Table Header
    col_width = 18
    header = f"{'Metric':<20} | {'M1 (Trend)':<{col_width}} | {'M2 (Revert)':<{col_width}} | {'Combined Portfolio':<{col_width}}"
    print(header)
    print("─"*85)
    
    results_map = {}
    for mod_name in ["M1", "M2", "Combined"]:
        data = stats[mod_name]
        if data:
            wr = (len([x for x in data if x > 0]) / len(data)) * 100
            ev = sum(data) / len(data)
            count = len(data)
            results_map[mod_name] = [f"{count} signals", f"{wr:.2f}%", f"{ev:+.2f}%"]
        else:
            results_map[mod_name] = ["0 signals", "0.00%", "0.00%"]

    print(f"{'Total Signals':<20} | {results_map['M1'][0]:<{col_width}} | {results_map['M2'][0]:<{col_width}} | {results_map['Combined'][0]:<{col_width}}")
    print(f"{'Win Rate':<20} | {results_map['M1'][1]:<{col_width}} | {results_map['M2'][1]:<{col_width}} | {results_map['Combined'][1]:<{col_width}}")
    print(f"{'Expected Value':<20} | {results_map['M1'][2]:<{col_width}} | {results_map['M2'][2]:<{col_width}} | {results_map['Combined'][2]:<{col_width}}")
    print(f"\nRegimes Detected     : {', '.join(regimes)}")
    print("─"*75)

def main():
    universe_dict, ihsg_data = load_cached_data()
    if not universe_dict:
        print("❌ Cache missing or incomplete. Run fetch script with 2025 start date.")
        return

    run_comparative_scenario("SIDEWAYS PING-PONG", "2025-05-01", universe_dict, ihsg_data)
    run_comparative_scenario("BULL MARKET DIP-BUYING", "2025-11-01", universe_dict, ihsg_data)
    run_comparative_scenario("CRASH CAPITULATION", "2026-03-02", universe_dict, ihsg_data)

if __name__ == "__main__":
    main()