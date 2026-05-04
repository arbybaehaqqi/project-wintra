import os
import pandas as pd
import numpy as np
from datetime import datetime

# Import all models as per tree_manifest
from core.models.m5_defensive import DefensiveModel
from core.models.m6_high_beta import HighBetaModel
from core.models.m7_washout import WashoutModel
from core.models.m8_camarilla import RangeScalperModel

# Configuration
CACHE_DIR = "core/data/intraday_cache"

# ANSI Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
GRAY = "\033[90m"
RESET = "\033[0m"

def run_watchdog_training():
    print(f"\n{CYAN}🏗️ WINTRA WATCHDOG PERFORMANCE TRAINING (REAL-SCENARIO SIMULATION){RESET}")
    print(f"{GRAY}Goal: Audit the Unified Hierarchy (Defense > Washout > Momentum > Range){RESET}\n")

    # Initialize Engines
    # Tightened M5 to 0.55 for better protection against "Gap & Crap"
    m5 = DefensiveModel(min_wick_ratio=0.55, require_red=True)
    m6 = HighBetaModel(min_itr=3.0, min_resilience=0.45) 
    m7 = WashoutModel(min_resilience=0.6, drop_req=3.0) 
    m8 = RangeScalperModel(min_itr=2.0)

    # Performance Tracking
    portfolio_pnl = []
    daily_stats = {} # Key: Date, Value: List of returns
    
    audit = {
        "m6_signals": 0,
        "m6_returns": [],
        "m5_vetoes": 0,
        "m7_triggers": 0,
        "m7_returns": [],
        "m8_triggers": 0,
        "m8_returns": [],
        "trades_executed": 0
    }

    # 1. LOAD DATA & ALIGN BY DATE
    all_data = {}
    all_dates = set()
    
    if not os.path.exists(CACHE_DIR):
        print(f"{RED}❌ Error: Cache directory {CACHE_DIR} not found.{RESET}")
        return

    files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".csv")]
    for f in files:
        ticker = f.split("_")[0]
        try:
            df = pd.read_csv(os.path.join(CACHE_DIR, f))
            
            # Robust Time Parsing
            time_col = next((c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()), None)
            
            if time_col:
                df[time_col] = pd.to_datetime(df[time_col])
                df.set_index(time_col, inplace=True)
            else:
                df.index = pd.to_datetime(df.index)
            
            # UTC Patch
            if not df.empty and df.index.hour[0] < 7:
                df.index = df.index + pd.Timedelta(hours=7)
            
            # Group by day
            daily = {date: group for date, group in df.groupby(df.index.date)}
            all_data[ticker] = daily
            all_dates.update(daily.keys())
        except Exception as e:
            continue

    sorted_dates = sorted(list(all_dates))
    print(f"📡 Synced {len(all_data)} tickers across {len(sorted_dates)} trading days.\n")

    # 2. ITERATE DAY-BY-DAY (The "Real Scenario" Loop)
    for i in range(len(sorted_dates) - 1):
        d1 = sorted_dates[i]   # Yesterday
        d2 = sorted_dates[i+1] # Today (Execution Day)
        
        daily_trades = []
        
        for ticker, ticker_data in all_data.items():
            if d1 not in ticker_data or d2 not in ticker_data: continue
            
            yest_df = ticker_data[d1]
            today_df = ticker_data[d2]
            
            if len(today_df) < 20: continue
            
            # --- MORNING PREP (D1) ---
            has_m6, _ = m6.evaluate(yest_df)
            has_m7, _ = m7.evaluate(ticker, yest_df)
            has_m8, m8_plan = m8.evaluate(ticker, yest_df)
            
            # --- LIVE EXECUTION (D2) ---
            # 🚨 Check M5 Defense (09:30 Check)
            is_trap, _ = m5.evaluate(today_df)
            
            # 🚀 Case 1: Model 6 Breakout
            if has_m6:
                audit["m6_signals"] += 1
                if is_trap:
                    audit["m5_vetoes"] += 1
                else:
                    first_bar = today_df.index[0]
                    orb_high = today_df.loc[first_bar : first_bar + pd.Timedelta(minutes=15)]['High'].max()
                    if today_df['High'].max() > orb_high:
                        ret = ((today_df['Close'].iloc[-1] - orb_high) / orb_high) * 100
                        daily_trades.append(ret)
                        audit["m6_returns"].append(ret)
                        audit["trades_executed"] += 1

            # 🩸 Case 2: Model 7 Washout
            if has_m7 and not is_trap:
                t_open = today_df['Open'].iloc[0]
                entry = t_open * (1 - (m7.drop_req / 100))
                if today_df['Low'].min() <= entry:
                    ret = ((today_df['Close'].iloc[-1] - entry) / entry) * 100
                    daily_trades.append(ret)
                    audit["m7_returns"].append(ret)
                    audit["m7_triggers"] += 1
                    audit["trades_executed"] += 1

            # 🏓 Case 3: Model 8 Camarilla
            if has_m8 and not is_trap:
                s3 = m8_plan['Buy_Zone']
                if today_df['Low'].min() <= s3 and today_df['Open'].iloc[0] >= s3:
                    ret = ((today_df['Close'].iloc[-1] - s3) / s3) * 100
                    daily_trades.append(ret)
                    audit["m8_returns"].append(ret)
                    audit["m8_triggers"] += 1
                    audit["trades_executed"] += 1

        if daily_trades:
            daily_pnl = np.mean(daily_trades)
            portfolio_pnl.extend(daily_trades)
            daily_stats[d2] = daily_pnl

    # 3. FINAL AUDIT REPORT
    print(f"📊 {MAGENTA}WATCHDOG UNIFIED PERFORMANCE REPORT{RESET}")
    print("─"*85)
    
    if portfolio_pnl:
        wr = (len([x for x in portfolio_pnl if x > 0]) / len(portfolio_pnl)) * 100
        avg_ev = np.mean(portfolio_pnl)
        total_acc = np.sum(portfolio_pnl)
        
        m5_efficiency = (audit["m5_vetoes"] / audit["m6_signals"]) * 100 if audit["m6_signals"] > 0 else 0
        
        print(f"Total Signals Potential : {audit['m6_signals'] + audit['m7_triggers'] + audit['m8_triggers']}")
        print(f"M5 Vetoes (Aborted)     : {audit['m5_vetoes']} ({m5_efficiency:.1f}% Shield Efficiency)")
        print(f"Trades Executed         : {audit['trades_executed']}")
        print("─"*85)
        
        # Engine Breakdown
        for engine, ret_list in [("M6 Breakout", audit["m6_returns"]), 
                                 ("M7 Washout ", audit["m7_returns"]), 
                                 ("M8 Scalper  ", audit["m8_returns"])]:
            if ret_list:
                e_wr = (len([x for x in ret_list if x > 0]) / len(ret_list)) * 100
                e_ev = np.mean(ret_list)
                print(f" {engine} | Trades: {len(ret_list):<4} | Win%: {e_wr:>5.1f}% | EV: {GREEN if e_ev > 0 else RED}{e_ev:>+6.3f}%{RESET}")
        
        print("─"*85)
        print(f"TOTAL PORTFOLIO WIN RATE : {wr:.2f}%")
        print(f"TOTAL PORTFOLIO EV       : {GREEN if avg_ev > 0 else RED}{avg_ev:+.3f}%{RESET}")
        print(f"CUMULATIVE RETURN        : {GREEN if total_acc > 0 else RED}{total_acc:+.2f}%{RESET}")
        print("─"*85)
        
        print(f"\n{CYAN}📈 RECENT DAILY PERFORMANCE (Virtual Portfolio):{RESET}")
        sorted_daily = sorted(daily_stats.items(), reverse=True)[:5]
        for dt, pnl in sorted_daily:
            color = GREEN if pnl > 0 else RED
            print(f" {dt} : {color}{pnl:>+6.2f}%{RESET}")
    else:
        print(f"{YELLOW}⚠️ No trades were executed in the 60-day period.{RESET}")
    
    print("\n" + "═"*85 + "\n")

if __name__ == "__main__":
    run_watchdog_training()
