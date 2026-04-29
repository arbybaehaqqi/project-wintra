import os
import json
import io
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from datetime import datetime, timedelta

# Import the finalized optimized models
from core.models.m1_trend import TrendModel as M1       # Legacy signature
from core.models.m2_revert_opt import RevertModel as M2 # Optimized signature
from core.models.m3_breakout import BreakoutModel as M3 # Optimized signature
from core.models.m4_leadership import LeadershipModel as M4 # Optimized signature

CACHE_FILE = os.path.join("core", "data", "m2_training_cache.json")

class WintraTournament:
    """
    The Morning Report Priority Engine.
    Dynamically weights and scores signals based on the current market regime
    using the optimized historical Expected Value (EV) and Win Rate data.
    """
    REGIME_WEIGHTS = {
        "BULL": {
            "M4_Alpha": 0.50,    # Dominant in Bull (+2.41% EV)
            "M1_Trend": 0.30,    # Solid Workhorse (+1.31% EV)
            "M3_Breakout": 0.20, # Vertical Velocity (+1.02% EV)
            "M2_Revert": 0.00    # Disabled (Value Trap in Bull, -5.00% EV)
        },
        "BEAR": {
            "M2_Revert": 0.40,   # Crash Capitulation King (+7.82% EV)
            "M1_Trend": 0.35,    # Elite Volume Guard (+4.12% EV)
            "M3_Breakout": 0.15, # Occasional strong bounce (+3.54% EV)
            "M4_Alpha": 0.10     # Weak in crashes (+0.91% EV)
        },
        "SIDEWAYS": {
            "M4_Alpha": 0.35,    # Range Outperformer (+2.43% EV)
            "M1_Trend": 0.35,    # Core Momentum (+2.20% EV)
            "M3_Breakout": 0.20, # Range Breakouts (+1.72% EV)
            "M2_Revert": 0.10    # Rare but elite range floor (+7.33% EV)
        }
    }

    @staticmethod
    def rank_candidates(candidates, regime):
        """
        Applies the Regime Weights to raw model scores to create a unified Top 5 list.
        Expects a list of dicts: [{'ticker': 'GOTO', 'model': 'M4_Alpha', 'raw_score': 15.2}, ...]
        """
        weights = WintraTournament.REGIME_WEIGHTS.get(regime, WintraTournament.REGIME_WEIGHTS["SIDEWAYS"])
        for c in candidates:
            model_weight = weights.get(c['model'], 0)
            # Final Conviction Score = Raw indicator strength * Regime Authority Weight
            c['tournament_score'] = c['raw_score'] * model_weight
            
        return sorted(candidates, key=lambda x: x['tournament_score'], reverse=True)


def load_cached_data():
    if not os.path.exists(CACHE_FILE):
        return None, None
    print(f"📂 Loading Wintra Cache...")
    with open(CACHE_FILE, 'r') as f:
        cache = json.load(f)
    ihsg = pd.read_json(io.StringIO(cache['ihsg']))
    ihsg.index = pd.to_datetime(ihsg.index)
    universe = {t: pd.read_json(io.StringIO(df)) for t, df in cache['tickers'].items()}
    for t in universe: universe[t].index = pd.to_datetime(universe[t].index)
    return universe, ihsg

def evaluate_perf(df, entry_date, stop_loss_limit):
    """Universal T+3 Evaluator"""
    curr_data = df.loc[df.index < pd.to_datetime(entry_date)]
    if curr_data.empty: return 0.0
    entry_price = curr_data['Close'].iloc[-1]
    
    future = df.loc[df.index >= pd.to_datetime(entry_date)].head(3)
    if future.empty: return 0.0
    
    max_high = future['High'].max()
    min_low = future['Low'].min()
    actual_close = future['Close'].iloc[-1]
    
    potential_peak = ((max_high - entry_price) / entry_price) * 100
    potential_drop = ((min_low - entry_price) / entry_price) * 100
    standard_perf = ((actual_close - entry_price) / entry_price) * 100
    
    if potential_drop <= stop_loss_limit:
        return stop_loss_limit
    return (standard_perf + potential_peak) / 2

def run_master_scenario(scenario_name, start_date_str, universe, ihsg, duration_days=90):
    print(f"\n🌍 SCENARIO: {scenario_name} ({start_date_str} for {duration_days} days)")
    
    # Simulate Regime Detection to show active Tournament Weights
    m1 = M1()
    initial_ihsg = ihsg.loc[ihsg.index < pd.to_datetime(start_date_str)]['Close']
    if not initial_ihsg.empty:
        initial_regime = m1.detect_regime(initial_ihsg)
        active_weights = WintraTournament.REGIME_WEIGHTS.get(initial_regime, {})
        weight_str = " | ".join([f"{k}: {v*100:.0f}%" for k, v in active_weights.items() if v > 0])
        print(f"⚖️ Tournament Priority ({initial_regime}): {weight_str}")
        
    print("─"*95)
    
    m2, m3, m4 = M2(), M3(), M4()
    start_sim = datetime.strptime(start_date_str, "%Y-%m-%d")
    test_dates = [(start_sim + timedelta(days=x)).strftime("%Y-%m-%d") for x in range(duration_days)]
    
    results = {"M1_Trend": [], "M2_Revert": [], "M3_Breakout": [], "M4_Alpha": []}
    
    for d in test_dates:
        dt = pd.to_datetime(d)
        if ihsg.empty or dt not in ihsg.index: continue
        ihsg_morning = ihsg.loc[ihsg.index < dt]['Close']
        if ihsg_morning.empty: continue
        
        regime = m1.detect_regime(ihsg_morning)
        # Dynamic Stop Loss
        sl_trend = -3.0 if regime == "BULL" else -4.0
        sl_revert = -5.0
        sl_breakout = -3.5
        
        for t, df in universe.items():
            morning = df.loc[df.index < dt]
            if len(morning) < 55: continue
            
            c, v, o, h, l = morning['Close'], morning['Volume'], morning['Open'], morning['High'], morning['Low']
            
            # --- M1 Evaluation (LEGACY Signature: close, vol, ihsg) ---
            if m1.evaluate(c, v, ihsg_morning):
                results["M1_Trend"].append(evaluate_perf(df, d, sl_trend))
            
            # --- M2 Evaluation (OPT Signature: c, v, o, h, l, ihsg) ---
            if m2.evaluate(c, v, o, h, l, ihsg_morning):
                results["M2_Revert"].append(evaluate_perf(df, d, sl_revert))
            
            # --- M3 Evaluation (OPT Signature: c, v, h, l, ihsg) ---
            if m3.evaluate(c, v, h, l, ihsg_morning):
                results["M3_Breakout"].append(evaluate_perf(df, d, sl_breakout))
            
            # --- M4 Evaluation (OPT Signature: c, v, o, h, ihsg) ---
            if m4.evaluate(c, v, o, h, ihsg_morning):
                results["M4_Alpha"].append(evaluate_perf(df, d, sl_trend))

    # Print Formatted Results
    print(f"{'Engine':<15} | {'Signals':<10} | {'Win Rate':<15} | {'Expected Value'}")
    print("─"*95)
    
    total_signals, total_wins, total_ev = 0, 0, 0
    
    for model_name, returns in results.items():
        if not returns:
            print(f"{model_name:<15} | {'0':<10} | {'0.00%':<15} | +0.00%")
            continue
            
        wins = len([x for x in returns if x > 0])
        wr = (wins / len(returns)) * 100
        ev = sum(returns) / len(returns)
        
        total_signals += len(returns)
        total_wins += wins
        total_ev += sum(returns)
        
        print(f"{model_name:<15} | {len(returns):<10} | {wr:.2f}%{'':<9} | {ev:+.2f}%")
        
    print("─"*95)
    if total_signals > 0:
        overall_wr = (total_wins / total_signals) * 100
        overall_ev = total_ev / total_signals
        print(f"**PORTFOLIO** | **{total_signals:<8}** | **{overall_wr:.2f}%**{'':<8} | **{overall_ev:+.2f}%**")

def main():
    print("🚀 WINTRA STAGE 4: MASTER SYSTEM EVALUATION & TOURNAMENT PREP")
    print("Aggregating optimized production engines (M1, M2, M3, M4)...")
    
    universe, ihsg = load_cached_data()
    if not universe: return

    run_master_scenario("SIDEWAYS PING-PONG", "2025-05-01", universe, ihsg, 90)
    run_master_scenario("BULL MARKET DOMINANCE", "2025-11-01", universe, ihsg, 90)
    run_master_scenario("CRASH CAPITULATION", "2026-03-02", universe, ihsg, 90)
    
    # 6-Month Mixed Market Stress Test (180 Days)
    run_master_scenario("6-MONTH MIXED MARKET (Bull -> Crash)", "2025-10-01", universe, ihsg, 180)

if __name__ == "__main__":
    main()
