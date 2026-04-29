import os
import json
import io
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from datetime import datetime, timedelta
from core.models.m3_breakout import BreakoutModel

# Constants for caching
CACHE_DIR = os.path.join("core", "data")
CACHE_FILE = os.path.join(CACHE_DIR, "m2_training_cache.json") # Reusing the master cache

def load_cached_data():
    """Loads market data from the local JSON file using StringIO."""
    if not os.path.exists(CACHE_FILE):
        return None, None
        
    print(f"📂 Loading training data from local cache...")
    with open(CACHE_FILE, 'r') as f:
        cache_payload = json.load(f)
        
    if cache_payload.get('metadata', {}).get('start_date') != "2025-01-01":
        print("⚠️ Cache is too old. Run fetch on m2 script first.")
        return None, None

    ihsg_data = pd.read_json(io.StringIO(cache_payload['ihsg']))
    ihsg_data.index = pd.to_datetime(ihsg_data.index)
    
    universe_dict = {}
    for ticker, df_json in cache_payload['tickers'].items():
        df = pd.read_json(io.StringIO(df_json))
        df.index = pd.to_datetime(df.index)
        universe_dict[ticker] = df
        
    return universe_dict, ihsg_data

def simulate_morning_report(date_str, universe_data, ihsg_data):
    """Simulates the morning report using Model 3 (Velocity Engine)."""
    m3 = BreakoutModel()
    candidates = []

    ihsg_morning = None
    if not ihsg_data.empty:
        ihsg_mask = ihsg_data.index < pd.to_datetime(date_str)
        ihsg_morning = ihsg_data.loc[ihsg_mask]['Close']

    current_regime = m3.detect_regime(ihsg_morning)

    for ticker, df in universe_data.items():
        morning_mask = df.index < pd.to_datetime(date_str)
        morning_data = df.loc[morning_mask]
        
        # M3 requires at least 50 days of data for SMA50 and 40-day lookbacks
        if len(morning_data) < 55: continue
        
        if m3.evaluate(
            close_prices=morning_data['Close'], 
            volume_series=morning_data['Volume'], 
            high_prices=morning_data['High'],
            low_prices=morning_data['Low'],
            market_index_series=ihsg_morning
        ):
            price_last_close = morning_data['Close'].iloc[-1]
            strength_score = m3.get_breakout_strength(morning_data['Close'], morning_data['Volume'])
            
            # T+3 Swing Evaluation
            future_data = df.loc[df.index >= pd.to_datetime(date_str)].head(3)
            
            if not future_data.empty:
                max_high = future_data['High'].max()
                min_low = future_data['Low'].min()
                actual_close = future_data['Close'].iloc[-1]
                
                potential_peak = ((max_high - price_last_close) / price_last_close) * 100
                potential_drop = ((min_low - price_last_close) / price_last_close) * 100
                standard_perf = ((actual_close - price_last_close) / price_last_close) * 100
                
                # BREAKOUT STOP LOSS: Tight -3.5%
                stop_limit = -3.5 
                
                if potential_drop <= stop_limit:
                    final_perf = stop_limit 
                else:
                    final_perf = (standard_perf + potential_peak) / 2
                
                candidates.append({'ticker': ticker, 'strength': strength_score, 'perf': final_perf})
                
    # Sort by Volume Surge multiplier (highest conviction breakouts first)
    candidates.sort(key=lambda x: x['strength'], reverse=True)
    # Cap to top 5 signals per day to mimic the Morning Report limits
    return candidates[:5], current_regime

def run_scenario(scenario_name, start_date_str, universe_dict, ihsg_data):
    print(f"\n🧪 SCENARIO: {scenario_name}")
    print("─"*65)
    
    start_sim = datetime.strptime(start_date_str, "%Y-%m-%d")
    test_dates = [(start_sim + timedelta(days=x)).strftime("%Y-%m-%d") for x in range(90)]
    all_stats = []
    regimes_detected = set()
    
    for d in test_dates:
        day_dt = pd.to_datetime(d)
        if ihsg_data.empty or day_dt not in ihsg_data.index: continue
        
        # Higher cap for breakouts since we are hunting volume
        if len(all_stats) >= 100: break

        results, regime = simulate_morning_report(d, universe_dict, ihsg_data)
        regimes_detected.add(regime)
        for res in results: all_stats.append(res['perf'])

    if all_stats:
        wins = [x for x in all_stats if x > 0]
        win_rate = (len(wins) / len(all_stats)) * 100
        ev = sum(all_stats)/len(all_stats)
        
        print(f"Detected Regime : {', '.join(regimes_detected)}")
        print(f"Signals Gen.    : {len(all_stats)}")
        print(f"Win Rate        : {win_rate:.2f}%")
        print(f"Expected Value  : {ev:+.2f}%")
    else:
        print(f"Detected Regime : {', '.join(regimes_detected)}")
        print(f"⚠️ No signals generated. The Model correctly stayed out of the market.")
    print("─"*65)

def main():
    print("🚀 WINTRA STAGE 2 TRAINING: MODEL 3 (BREAKOUT ENGINE)")
    
    universe_dict, ihsg_data = load_cached_data()
    if not universe_dict:
        print("❌ Cannot run. Cache missing. Please run `train_m2_all_regimes.py` with force_refresh=True first.")
        return

    # Scenario 1: Sideways Market (Mid 2025)
    run_scenario("SIDEWAYS PING-PONG", "2025-05-01", universe_dict, ihsg_data)

    # Scenario 2: Bull Market (Late 2025 / Early 2026)
    run_scenario("BULL MARKET BREAKOUTS", "2025-11-01", universe_dict, ihsg_data)

    # Scenario 3: Bear Market (The Crash of March 2026)
    run_scenario("CRASH CAPITULATION", "2026-03-02", universe_dict, ihsg_data)

if __name__ == "__main__":
    main()
