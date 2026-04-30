import os
import pandas as pd
import numpy as np

# ANSI Colors for Terminal
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
RESET = "\033[0m"

class M6_HighBeta:
    """Model 6: The Strength Rider (Buy shallow dips, sell at highs)"""
    def __init__(self):
        self.name = "M6_HighBeta"

    def evaluate(self, df):
        daily_groups = df.groupby(df.index.date)
        daily_ranges, close_positions = [], []
        
        for date, group in daily_groups:
            if len(group) < 10: continue # Skip incomplete days
            
            o = group['Open'].iloc[0]
            h = group['High'].max()
            l = group['Low'].min()
            c = group['Close'].iloc[-1]
            
            # Calculate Intraday True Range (ITR) %
            itr = ((h - l) / o) * 100
            daily_ranges.append(itr)
            
            # Calculate Close Position (Resilience)
            range_val = h - l
            if range_val > 0:
                close_positions.append((c - l) / range_val)

        avg_itr = np.mean(daily_ranges) if daily_ranges else 0
        avg_resilience = np.mean(close_positions) if close_positions else 0
        
        # M6 Rules: High Volatility (>2.5%) + Closes near the High (>0.55)
        if avg_itr >= 2.5 and avg_resilience >= 0.55:
            # Generate Today's Trade Zones based on last available data
            yest_c = df['Close'].iloc[-1]
            # Approximate the high of the last trading session
            yest_h = df['High'].iloc[-66:].max() if len(df) >= 66 else df['High'].max()
            
            return True, {
                "ITR": avg_itr,
                "Buy_Zone": yest_c * 0.99,   # Target: Buy a 1% morning dip
                "Target": yest_h,            # Target: Yesterday's high
                "Cut_Loss": yest_c * 0.97    # Stop: Cut if it drops 3%
            }
        return False, {}


class M7_Washout:
    """Model 7: The Panic Buyer (Buy deep morning crashes, sell the recovery)"""
    def __init__(self):
        self.name = "M7_Washout"

    def evaluate(self, df):
        daily_groups = df.groupby(df.index.date)
        washout_days = 0
        recovery_days = 0
        avg_drop = []

        for date, group in daily_groups:
            if len(group) < 20: continue
            
            day_open = group['Open'].iloc[0]
            day_close = group['Close'].iloc[-1]
            
            # Isolate the first 90 minutes (09:00 - 10:30)
            morning_mask = (group.index.hour == 9) | ((group.index.hour == 10) & (group.index.minute <= 30))
            morning_data = group.loc[morning_mask]
            
            if morning_data.empty: continue
            
            morning_low = morning_data['Low'].min()
            drop_pct = ((morning_low - day_open) / day_open) * 100
            
            # M7 Signature: Did it drop more than 2% in the morning?
            if drop_pct <= -2.0:
                washout_days += 1
                avg_drop.append(drop_pct)
                # Did it recover back near the open price by the end of the day?
                if day_close >= day_open * 0.995: 
                    recovery_days += 1

        recovery_rate = (recovery_days / washout_days * 100) if washout_days > 0 else 0
        avg_panic_drop = np.mean(avg_drop) if avg_drop else 0
        
        # M7 Rules: Must happen frequently (>3 times) and recover reliably (>65% of the time)
        if washout_days >= 3 and recovery_rate >= 65.0:
            last_close = df['Close'].iloc[-1]
            
            return True, {
                "Recovery_Rate": recovery_rate,
                "Avg_Drop": avg_panic_drop,
                "Buy_Zone": last_close * (1 + (avg_panic_drop/100)), # Set trap at historical drop depth
                "Target": last_close,                                # Target the recovery to breakeven
                "Cut_Loss": last_close * (1 + ((avg_panic_drop - 1.5)/100)) # Cut 1.5% below the usual bottom
            }
        return False, {}


def run_intraday_scanners():
    print(f"\n{CYAN}⚔️ WINTRA DUAL-PLAYBOOK GENERATOR{RESET}")
    print("Scanning Local Cache for M6 (Strength) and M7 (Washout)...")
    print("─"*75)
    
    cache_dir = "core/data/intraday_cache"
    if not os.path.exists(cache_dir) or not os.listdir(cache_dir):
        print(f"{RED}⚠️ Cache directory empty or not found. Please run core/data_fetcher.py first.{RESET}")
        return

    m6_picks = []
    m7_picks = []
    m6, m7 = M6_HighBeta(), M7_Washout()

    # Process all CSVs in the cache
    for filename in os.listdir(cache_dir):
        if not filename.endswith(".csv"): continue
        
        ticker = filename.split("_")[0]
        filepath = os.path.join(cache_dir, filename)
        
        try:
            df = pd.read_csv(filepath)
            if df.empty or 'Datetime' not in df.columns:
                continue

            # Standardize datetime index
            df['Datetime'] = pd.to_datetime(df['Datetime'])
            df.set_index('Datetime', inplace=True)
            
            # Evaluate Model 6
            pass_m6, m6_metrics = m6.evaluate(df)
            if pass_m6: m6_picks.append((ticker, m6_metrics))
                
            # Evaluate Model 7
            pass_m7, m7_metrics = m7.evaluate(df)
            if pass_m7: m7_picks.append((ticker, m7_metrics))
                
        except Exception as e:
            continue # Silently skip malformed files

    # --- PRINT M6 PLAYBOOK ---
    print(f"\n{GREEN}📈 PLAYBOOK A: THE STRENGTH RIDERS (MODEL 6){RESET}")
    print(f"{GRAY}Strategy: Buy the shallow dip. Sell the breakout.{RESET}")
    print(f"{'Ticker':<8} | {'ITR Vol':<8} | {'Buy Zone (Low)':<15} | {'Target (High)':<15} | {'Cut Loss'}")
    print("-" * 75)
    if not m6_picks:
        print("No stocks met the criteria today.")
    else:
        for t, m in sorted(m6_picks, key=lambda x: x[1]['ITR'], reverse=True)[:5]:
            print(f"{t:<8} | {m['ITR']:>5.1f}%   | Rp {m['Buy_Zone']:<12,.0f} | Rp {m['Target']:<12,.0f} | Rp {m['Cut_Loss']:,.0f}")

    # --- PRINT M7 PLAYBOOK ---
    print(f"\n{MAGENTA}🩸 PLAYBOOK B: THE PANIC BUYERS (MODEL 7){RESET}")
    print(f"{GRAY}Strategy: Wait for the morning crash. Buy the blood. Sell the recovery.{RESET}")
    print(f"{'Ticker':<8} | {'Win Rate':<8} | {'Washout Zone (Buy)':<18} | {'Target (Open)':<13} | {'Cut Loss'}")
    print("-" * 75)
    if not m7_picks:
        print("No stocks met the criteria today.")
    else:
        for t, m in sorted(m7_picks, key=lambda x: x[1]['Recovery_Rate'], reverse=True)[:5]:
            print(f"{t:<8} | {m['Recovery_Rate']:>5.1f}%   | Rp {m['Buy_Zone']:<15,.0f} | Rp {m['Target']:<10,.0f} | Rp {m['Cut_Loss']:,.0f}")
        
    print("\n" + "═"*75 + "\n")

if __name__ == "__main__":
    run_intraday_scanners()