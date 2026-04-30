import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import pytz

# Import all Intraday & Defensive Models
from core.models.m5_defensive import DefensiveModel
from core.models.m6_high_beta import HighBetaModel
from core.models.m7_washout import WashoutModel
from core.models.m8_camarilla import RangeScalperModel

# ANSI Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
GRAY = "\033[90m"
MAGENTA = "\033[95m"
RESET = "\033[0m"

def get_wib_now():
    """Returns current time in Jakarta."""
    wib_tz = pytz.timezone('Asia/Jakarta')
    return datetime.now(wib_tz)

def run_intraday_watchdog():
    now_wib = get_wib_now()
    log_time = now_wib.strftime("%H:%M:%S WIB")
    
    print(f"\n" + "═"*95)
    print(f"{CYAN}⚡ WINTRA UNIFIED INTRADAY WATCHDOG | {log_time}{RESET}")
    print("═"*95)

    # 1. Load Universe
    data_path = os.path.join("core", "data", "idx80_list.json")
    if not os.path.exists(data_path):
        print(f"{RED}❌ Could not find IDX80 list. Run core/data_fetcher.py first.{RESET}")
        return
        
    with open(data_path, 'r') as f:
        universe = json.load(f).get('tickers', [])
        
    yf_tickers = [f"{t}.JK" for t in universe]
    print(f"📡 Fetching live 5-minute data for {len(yf_tickers)} tickers...")
    
    # We fetch 5 days of 5m data to ensure we have "yesterday" and "today"
    data = yf.download(yf_tickers, period="5d", interval="5m", progress=False)
    
    m5 = DefensiveModel()
    m6 = HighBetaModel()
    m7 = WashoutModel()
    m8 = RangeScalperModel()
    
    alerts_m6 = []
    alerts_m7 = []
    alerts_m8 = []
    traps_m5 = []

    print(f"🧠 Processing Intraday Matrices...\n")

    for ticker in universe:
        symbol = f"{ticker}.JK"
        try:
            # Extract single ticker dataframe
            df = pd.DataFrame({
                'Open': data['Open'][symbol],
                'High': data['High'][symbol],
                'Low': data['Low'][symbol],
                'Close': data['Close'][symbol],
                'Volume': data['Volume'][symbol]
            }).dropna()
            
            if len(df) < 66: continue
            
            # Align timezones if necessary
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
                
            # Split into Historical (for setup) and Today (for live checking)
            daily_groups = [group for _, group in df.groupby(df.index.date)]
            if len(daily_groups) < 2: continue
            
            historical_df = pd.concat(daily_groups[:-1]) # Up to yesterday
            today_df = daily_groups[-1]                  # Today's live data
            
            if today_df.empty: continue
            
            curr_price = today_df['Close'].iloc[-1]
            today_open = today_df['Open'].iloc[0]
            
            # -----------------------------------------------------------------
            # 🚨 M5 DEFENSIVE CHECK (Is this stock a trap today?)
            # -----------------------------------------------------------------
            is_trap, trap_info = m5.evaluate(today_df, historical_df)
            if is_trap:
                traps_m5.append({'ticker': ticker, 'info': trap_info})
                continue # If it's a trap, skip all offensive buy checks!

            # -----------------------------------------------------------------
            # 🚀 M6 ORB BREAKOUT CHECK
            # -----------------------------------------------------------------
            has_m6_setup, m6_plan = m6.evaluate(historical_df)
            if has_m6_setup:
                # Calculate live ORB
                morning_bars = today_df.between_time('09:00', '09:14')
                if not morning_bars.empty:
                    orb_high = morning_bars['High'].max()
                    if curr_price > orb_high:
                        status = f"{GREEN}🔥 BREAKOUT ACTIVE{RESET}"
                    else:
                        status = f"{GRAY}⏳ Waiting to break Rp {orb_high:,.0f}{RESET}"
                        
                    alerts_m6.append({'ticker': ticker, 'status': status, 'price': curr_price})

            # -----------------------------------------------------------------
            # 🩸 M7 WASHOUT CHECK (Panic Dip & Rip)
            # -----------------------------------------------------------------
            has_m7_setup, m7_plan = m7.evaluate(ticker, historical_df)
            if has_m7_setup:
                buy_zone = today_open * (1 - (m7.drop_req / 100))
                if curr_price <= buy_zone:
                    status = f"{GREEN}🩸 TRAP TRIGGERED! BUY NOW{RESET}"
                else:
                    status = f"{GRAY}⏳ Waiting for crash to Rp {buy_zone:,.0f}{RESET}"
                    
                alerts_m7.append({'ticker': ticker, 'status': status, 'price': curr_price})

            # -----------------------------------------------------------------
            # 🏓 M8 CAMARILLA RANGE SCALP CHECK
            # -----------------------------------------------------------------
            has_m8_setup, m8_plan = m8.evaluate(ticker, historical_df)
            if has_m8_setup:
                s3_buy_zone = m8_plan['Buy_Zone']
                # Gap down protection (abort if opened below S3)
                if today_open < s3_buy_zone:
                    status = f"{RED}❌ ABORT (Opened below S3){RESET}"
                elif curr_price <= s3_buy_zone:
                    status = f"{GREEN}🏓 S3 FLOOR HIT! BUY NOW{RESET}"
                else:
                    status = f"{GRAY}⏳ Waiting for S3 Floor Rp {s3_buy_zone:,.0f}{RESET}"
                    
                alerts_m8.append({'ticker': ticker, 'status': status, 'price': curr_price})

        except Exception as e:
            pass # Silently skip errors for individual tickers during live scan

    # --- PRINT RESULTS UI ---
    
    # 1. TRAPS
    if traps_m5:
        print(f"🚨 {RED}MODEL 5 DETECTED TRAPS (ABORT / DO NOT BUY){RESET}")
        print("─"*95)
        for trap in traps_m5:
            w = trap['info']['Wick_Ratio'] * 100
            print(f" ☠️ {trap['ticker'].ljust(6)} | Heavy Distribution Detected! Upper Wick: {w:.1f}% of 30m Range.")
        print("")

    # 2. BREAKOUTS
    print(f"🚀 {GREEN}MODEL 6 ORB BREAKOUTS (Strength Riders){RESET}")
    print("─"*95)
    if not alerts_m6: print(" No valid ORB setups today.")
    else:
        for a in alerts_m6: print(f" {a['ticker'].ljust(6)} | Price: {a['price']:>6,.0f} | {a['status']}")
    print("")

    # 3. WASHOUTS
    print(f"🩸 {MAGENTA}MODEL 7 WASHOUTS (Panic Buyers - Whitelist Only){RESET}")
    print("─"*95)
    if not alerts_m7: print(" No valid Washout traps set today.")
    else:
        for a in alerts_m7: print(f" {a['ticker'].ljust(6)} | Price: {a['price']:>6,.0f} | {a['status']}")
    print("")

    # 4. SCALPERS
    print(f"🏓 {CYAN}MODEL 8 CAMARILLA SCALPS (Range Bounce){RESET}")
    print("─"*95)
    if not alerts_m8: print(" No valid Camarilla setups today.")
    else:
        for a in alerts_m8: print(f" {a['ticker'].ljust(6)} | Price: {a['price']:>6,.0f} | {a['status']}")

    print("═"*95 + "\n")

if __name__ == "__main__":
    run_intraday_watchdog()