import os
import json
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from datetime import datetime, timedelta
from core.models.m1_trend import TrendModel

def simulate_morning_report(date_str, universe_data, ihsg_data):
    # Initialize Adaptive Model
    m1 = TrendModel()
    candidates = []

    ihsg_morning = None
    if not ihsg_data.empty:
        ihsg_mask = ihsg_data.index < pd.to_datetime(date_str)
        ihsg_morning = ihsg_data.loc[ihsg_mask]['Close']

    current_regime = m1.detect_regime(ihsg_morning)

    for ticker, df in universe_data.items():
        morning_mask = df.index < pd.to_datetime(date_str)
        morning_data = df.loc[morning_mask]
        if len(morning_data) < 50: continue
        
        if m1.evaluate(morning_data['Close'], morning_data['Volume'], ihsg_morning):
            ema_fast = ta.ema(morning_data['Close'], length=10).iloc[-1]
            price_last_close = morning_data['Close'].iloc[-1]
            prox = ((price_last_close - ema_fast) / ema_fast) * 100
            
            # T+3 Swing Analysis
            future_data = df.loc[df.index >= pd.to_datetime(date_str)].head(3)
            
            if not future_data.empty:
                max_high = future_data['High'].max()
                min_low = future_data['Low'].min()
                actual_close = future_data['Close'].iloc[-1]
                
                potential_peak = ((max_high - price_last_close) / price_last_close) * 100
                potential_drop = ((min_low - price_last_close) / price_last_close) * 100
                standard_perf = ((actual_close - price_last_close) / price_last_close) * 100
                
                # Stop Loss depends on regime
                stop_limit = -3.0 if current_regime == "BULL" else -5.0
                
                if potential_drop <= stop_limit:
                    final_perf = stop_limit
                else:
                    final_perf = (standard_perf + potential_peak) / 2
                
                candidates.append({'ticker': ticker, 'prox': prox, 'perf': final_perf})
                
    candidates.sort(key=lambda x: x['prox'])
    return candidates[:5], current_regime

def run_training(scenario_name, start_date, end_date):
    print(f"\n🎓 WINTRA ADAPTIVE TRAINING: {scenario_name}")
    print("─"*65)
    
    data_path = os.path.join("core", "data", "idx80_list.json")
    if not os.path.exists(data_path):
        universe = ["ANTM", "MEDC", "ASII", "BBCA", "TLKM", "AMMN", "ERAA", "SIDO", "TAPG", "PGAS", "ADRO"]
    else:
        with open(data_path, 'r') as f:
            universe = json.load(f).get('tickers', [])

    yf_tickers = [f"{t}.JK" for t in universe]
    data = yf.download(yf_tickers + ["^JKSE"], start="2025-01-01", end="2026-06-01", progress=False)
    
    universe_dict = {}
    ihsg_data = pd.DataFrame()
    for t in yf_tickers + ["^JKSE"]:
        try:
            ticker_df = pd.DataFrame({'Close': data['Close'][t], 'High': data['High'][t], 'Low': data['Low'][t], 'Volume': data['Volume'][t]}).dropna()
            if not ticker_df.empty:
                if t == "^JKSE": ihsg_data = ticker_df
                else: universe_dict[t.replace('.JK', '')] = ticker_df
        except: pass

    start_sim = datetime.strptime(start_date, "%Y-%m-%d")
    test_dates = [(start_sim + timedelta(days=x)).strftime("%Y-%m-%d") for x in range(90)]
    all_stats = []
    regimes_seen = set()
    
    for d in test_dates:
        day_dt = pd.to_datetime(d)
        if ihsg_data.empty or day_dt not in ihsg_data.index: continue
        if len(all_stats) >= 60: break

        results, regime = simulate_morning_report(d, universe_dict, ihsg_data)
        regimes_seen.add(regime)
        if not results: continue
        for res in results: all_stats.append(res['perf'])

    if all_stats:
        win_rate = (len([x for x in all_stats if x > 0]) / len(all_stats)) * 100
        ev = sum(all_stats)/len(all_stats)
        print(f"Stats  : {len(all_stats)} Signals | Win Rate: {win_rate:.2f}% | EV: {ev:+.2f}%")
        print(f"Nature : Adaptive ({', '.join(regimes_seen)})")
    else:
        print("⚠️ No signals. The 'Guard' nature kept you in cash.")

if __name__ == "__main__":
    # You can now toggle scenarios easily:
    run_training("SIDEWAYS TEST", "2025-05-01", "2025-08-01")
    run_training("BULL TEST", "2025-10-15", "2026-01-15")
    run_training("CRASH TEST", "2026-03-02", "2026-05-01")
