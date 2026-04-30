import os
import pandas as pd
import numpy as np
from datetime import datetime

# Attempt to import tabulate for pretty printing
try:
    from tabulate import tabulate
except ImportError:
    tabulate = None

# Import all Wintra Models
from core.models.m1_trend_opt import TrendModel
from core.models.m5_defensive import DefensiveModel
from core.models.m6_high_beta import HighBetaModel
from core.models.m7_washout import WashoutModel
from core.models.m8_camarilla import RangeScalperModel

# Configuration
CACHE_DIR = "core/data/intraday_cache"
DEBUG_MODE = True # Set to True to see why signals are being skipped

# ANSI Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
GRAY = "\033[90m"
RESET = "\033[0m"

def run_simulation():
    print(f"\n{CYAN}🚀 WINTRA PERFORMANCE SIMULATOR (V2.2 - ERROR RECOVERY){RESET}")
    print(f"{GRAY}Scanning cache for historical trade opportunities...{RESET}\n")

    # Initialize Engines - LOOSENED PARAMETERS FOR INITIAL TEST
    m5 = DefensiveModel(min_wick_ratio=0.6, require_red=True)
    m6 = HighBetaModel(min_itr=2.0, min_resilience=0.3) 
    m7 = WashoutModel(min_resilience=0.4, drop_req=1.5) 
    m8 = RangeScalperModel(min_itr=1.0)                 

    stats = {
        "M6 (Breakout)": {"trades": 0, "wins": 0, "returns": []},
        "M7 (Washout)": {"trades": 0, "wins": 0, "returns": []},
        "M8 (Scalper)": {"trades": 0, "wins": 0, "returns": []},
        "COMBINED (M6+M5)": {"trades": 0, "wins": 0, "returns": []}
    }

    diag = {"files": 0, "total_days": 0, "m6_setups": 0, "m7_setups": 0, "m8_setups": 0}

    files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".csv")]
    if not files:
        print(f"{RED}❌ No CSV files found in {CACHE_DIR}{RESET}")
        return

    # SCAN ALL FILES
    for filename in files:
        ticker = filename.split("_")[0]
        try:
            # BUG FIX: Handle different CSV header formats (Datetime vs Date vs Index)
            df_raw = pd.read_csv(os.path.join(CACHE_DIR, filename))
            
            # Find the time column regardless of exact naming
            time_col = next((c for c in df_raw.columns if 'date' in c.lower() or 'time' in c.lower()), None)
            
            if time_col:
                df_raw[time_col] = pd.to_datetime(df_raw[time_col])
                df_raw.set_index(time_col, inplace=True)
            else:
                # If no time column, assume index 0 is the datetime
                df_raw.index = pd.to_datetime(df_raw.index)
            
            df = df_raw.copy()
            
            # Timezone Correction
            if not df.empty and df.index.hour[0] < 7:
                df.index = df.index + pd.Timedelta(hours=7)
            
            diag["files"] += 1
            
            daily_groups = [g for _, g in df.groupby(df.index.date)]
            if len(daily_groups) < 2: 
                continue

            diag["total_days"] += len(daily_groups)

            # Trace counter per ticker
            trace_count = 0 

            for i in range(len(daily_groups) - 1):
                yest = daily_groups[i]
                today = daily_groups[i+1]
                
                # ---------------------------------------------------------
                # MODEL 6: MOMENTUM (ORB)
                # ---------------------------------------------------------
                has_m6, m6_info = m6.evaluate(yest)
                
                # TRACE CLEANUP: Only show if ITR > 0 to filter out data gaps/holidays
                itr = m6_info.get('ITR', 0)
                if not has_m6 and DEBUG_MODE and trace_count < 1 and itr > 0.1:
                    res = m6_info.get('Resilience', 0)
                    print(f"{GRAY}[TRACE] {ticker.ljust(5)} | M6 Fail | ITR:{itr:>4.1f}% | Res:{res:>4.2f}{RESET}")
                    trace_count += 1

                if has_m6:
                    diag["m6_setups"] += 1
                    first_bar = today.index[0]
                    end_orb = first_bar + pd.Timedelta(minutes=15)
                    morning_bars = today.loc[first_bar : end_orb]
                    
                    if not morning_bars.empty:
                        orb_high = morning_bars['High'].max()
                        trading_bars = today.loc[end_orb + pd.Timedelta(minutes=5) :]
                        if not trading_bars.empty:
                            if trading_bars['High'].max() > orb_high:
                                ret = ((today['Close'].iloc[-1] - orb_high) / orb_high) * 100
                                stats["M6 (Breakout)"]["trades"] += 1
                                stats["M6 (Breakout)"]["returns"].append(ret)
                                if ret > 0: stats["M6 (Breakout)"]["wins"] += 1
                                
                                is_trap, _ = m5.evaluate(today)
                                if not is_trap:
                                    stats["COMBINED (M6+M5)"]["trades"] += 1
                                    stats["COMBINED (M6+M5)"]["returns"].append(ret)
                                    if ret > 0: stats["COMBINED (M6+M5)"]["wins"] += 1

                # ---------------------------------------------------------
                # MODEL 7: WASHOUT
                # ---------------------------------------------------------
                has_m7, _ = m7.evaluate(ticker, yest)
                if has_m7:
                    diag["m7_setups"] += 1
                    t_open = today['Open'].iloc[0]
                    entry = t_open * (1 - (m7.drop_req / 100))
                    if today['Low'].min() <= entry:
                        ret = ((today['Close'].iloc[-1] - entry) / entry) * 100
                        stats["M7 (Washout)"]["trades"] += 1
                        stats["M7 (Washout)"]["returns"].append(ret)
                        if ret > 0: stats["M7 (Washout)"]["wins"] += 1

                # ---------------------------------------------------------
                # MODEL 8: CAMARILLA
                # ---------------------------------------------------------
                has_m8, m8_plan = m8.evaluate(ticker, yest)
                if has_m8:
                    diag["m8_setups"] += 1
                    s3 = m8_plan['Buy_Zone']
                    if today['Low'].min() <= s3:
                        ret = ((today['Close'].iloc[-1] - s3) / s3) * 100
                        stats["M8 (Scalper)"]["trades"] += 1
                        stats["M8 (Scalper)"]["returns"].append(ret)
                        if ret > 0: stats["M8 (Scalper)"]["wins"] += 1

        except Exception as e:
            if DEBUG_MODE: print(f"{RED}Error processing {ticker}: {e}{RESET}")
            continue

    # Final Output
    table_data = []
    for engine, s in stats.items():
        if s["trades"] > 0:
            wr = (s["wins"] / s["trades"]) * 100
            ev = np.mean(s["returns"])
            table_data.append([engine, s["trades"], f"{wr:.1f}%", f"{ev:+.3f}%"])

    print(f"\n📊 {MAGENTA}WINTRA SIMULATION RESULTS{RESET}")
    print("─"*85)
    print(f"Stats: Scanned {diag['files']} stocks ({diag['total_days']} total days).")
    print(f"Setups Found: M6: {diag['m6_setups']} | M7: {diag['m7_setups']} | M8: {diag['m8_setups']}")
    print("─"*85)
    
    if not table_data:
        print(f"{YELLOW}⚠️ Still no trades. Look at the [TRACE] logs above.{RESET}")
    elif tabulate:
        print(tabulate(table_data, headers=["Engine", "Trades", "Win Rate", "Avg EV"], tablefmt="psql"))
    else:
        for row in table_data: print(row)
    print("─"*85)

if __name__ == "__main__":
    run_simulation()