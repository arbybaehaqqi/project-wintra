import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import pandas_ta as ta

# 1. IMPORT MODELS
from core.models.m1_trend import TrendModel as M1
from core.models.m2_revert import RevertModel as M2
from core.models.m3_breakout import BreakoutModel as M3
from core.models.m4_leadership import LeadershipModel as M4
from core.models.m5_defensive import DefensiveModel as M5
from core.models.m6_high_beta import HighBetaModel as M6
from core.models.m7_washout import WashoutModel as M7
from core.models.m8_camarilla import RangeScalperModel as M8
from core.models.m9_controller import PortfolioController as M9

# ANSI Colors
CYAN, GREEN, YELLOW, RED, MAGENTA, GRAY, RESET = "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[95m", "\033[90m", "\033[0m"

# Historical Expected Values (EV%) for the Report Display
MODEL_EV = {
    "M1_Trend": "+1.86%", "M2_Revert": "+3.91%", "M3_Breakout": "+2.57%", 
    "M4_Alpha": "+2.41%", "M6_HighBeta": "+0.49%", "M7_Washout": "+1.15%", "M8_Camarilla": "+0.85%"
}

class TimeframeGauntlet:
    def __init__(self):
        self.m1, self.m2, self.m3, self.m4 = M1(), M2(), M3(), M4()
        self.m5, self.m6, self.m7, self.m8 = M5(), M6(), M7(), M8()
        self.m9 = M9()
        
        # Capital Allocation Slots
        self.balance = 100_000_000
        self.slots = {
            "SWING": {"max": 2, "held": []},       # 2 Slots for 1-5 day holds
            "SHORT_SWING": {"max": 1, "held": []}, # 1 Slot for overnight/2 day holds
            "BPJS": {"max": 1, "held": []}         # 1 Slot for Day Trades
        }
        self.history = []

    def fetch_market_data(self):
        print(f"{GRAY}📡 Fetching 65-days of market data for 1-Week Timeframe Test...{RESET}")
        list_path = os.path.join("core", "data", "idx80_list.json")
        if os.path.exists(list_path):
            with open(list_path, 'r') as f: universe = json.load(f).get('tickers', [])
        else:
            universe = ["BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ASII", "GOTO", "AMMN", "BREN", "SIDO", "MEDC", "ADRO", "PTBA"]
            
        yf_tickers = [f"{t}.JK" for t in universe]
        
        daily_data = yf.download(yf_tickers + ["^JKSE"], period="65d", interval="1d", progress=False)
        # FIX: Extended to 7d to bypass Yahoo's weekend/holiday truncation
        intraday_data = yf.download(yf_tickers, period="7d", interval="5m", progress=False)
        
        if daily_data.index.tz is not None: daily_data.index = daily_data.index.tz_localize(None)
        if intraday_data.index.tz is not None: intraday_data.index = intraday_data.index.tz_localize(None)
        
        # Standardize Intraday timezone to WIB
        if not intraday_data.empty and intraday_data.index.hour[0] < 7:
            intraday_data.index = intraday_data.index + pd.Timedelta(hours=7)
            
        return universe, daily_data, intraday_data

    def evaluate_day(self, date_str, universe, daily_data, intraday_data):
        dt = pd.to_datetime(date_str)
        ihsg_hist = daily_data['Close']["^JKSE"].loc[daily_data.index <= dt]
        if len(ihsg_hist) < 50: return None
        
        regime = self.m1.detect_regime(ihsg_hist)
        report = {"SWING": [], "SHORT_SWING": [], "BPJS": []}
        
        for ticker in universe:
            sym = f"{ticker}.JK"
            if sym not in daily_data['Close']: continue
            
            d_hist = pd.DataFrame({
                'Open': daily_data['Open'][sym], 'High': daily_data['High'][sym],
                'Low': daily_data['Low'][sym], 'Close': daily_data['Close'][sym], 'Volume': daily_data['Volume'][sym]
            }).loc[daily_data.index <= dt].dropna()
            
            if len(d_hist) < 50: continue
            
            c, v, o, h, l = d_hist['Close'], d_hist['Volume'], d_hist['Open'], d_hist['High'], d_hist['Low']
            atr = ta.atr(h, l, c, length=14).iloc[-1] if len(d_hist) > 14 else c.iloc[-1] * 0.02
            prev_price = c.iloc[-1]
            
            # --- SWING BUCKET (M1, M3, M4) ---
            if self.m1.evaluate(close_prices=c, volume_series=v, market_index_series=ihsg_hist):
                report["SWING"].append({'ticker': ticker, 'model': 'M1_Trend', 'raw_score': max(0, 100 - (self.m1.get_proximity(c)*5)), 'prev': prev_price, 'target': prev_price + (atr*2), 'ev': MODEL_EV['M1_Trend'], 'cat': 'SWING'})
            if self.m3.evaluate(close_prices=c, volume_series=v, high_prices=h, low_prices=l, market_index_series=ihsg_hist):
                report["SWING"].append({'ticker': ticker, 'model': 'M3_Breakout', 'raw_score': self.m3.get_breakout_strength(c, v)*25, 'prev': prev_price, 'target': prev_price + (atr*3), 'ev': MODEL_EV['M3_Breakout'], 'cat': 'SWING'})
            if self.m4.evaluate(close_prices=c, volume_series=v, open_prices=o, high_prices=h, market_index_series=ihsg_hist):
                report["SWING"].append({'ticker': ticker, 'model': 'M4_Alpha', 'raw_score': self.m4.get_alpha_score(c, ihsg_hist)*10, 'prev': prev_price, 'target': prev_price + (atr*2.5), 'ev': MODEL_EV['M4_Alpha'], 'cat': 'SWING'})

            # --- SHORT SWING BUCKET (M2, M6) ---
            if self.m2.evaluate(close_prices=c, volume_series=v, open_prices=o, high_prices=h, low_prices=l, market_index_series=ihsg_hist):
                report["SHORT_SWING"].append({'ticker': ticker, 'model': 'M2_Revert', 'raw_score': self.m2.get_elasticity_score(c)*15, 'prev': prev_price, 'target': ta.ema(c, length=20).iloc[-1], 'ev': MODEL_EV['M2_Revert'], 'cat': 'SHORT_SWING'})
            
            # M6 needs intraday history
            i_hist = pd.DataFrame({
                'Open': intraday_data['Open'][sym], 'High': intraday_data['High'][sym],
                'Low': intraday_data['Low'][sym], 'Close': intraday_data['Close'][sym], 'Volume': intraday_data['Volume'][sym]
            }).loc[intraday_data.index.date <= dt.date()].dropna()
            
            if not i_hist.empty:
                is_m6, _ = self.m6.evaluate(i_hist)
                if is_m6:
                    report["SHORT_SWING"].append({'ticker': ticker, 'model': 'M6_HighBeta', 'raw_score': 35.0, 'prev': prev_price, 'target': h.iloc[-1], 'ev': MODEL_EV['M6_HighBeta'], 'cat': 'SHORT_SWING'})
                
                # --- BPJS BUCKET (M7, M8) ---
                is_m7, m7_plan = self.m7.evaluate(ticker, i_hist)
                if is_m7:
                    report["BPJS"].append({'ticker': ticker, 'model': 'M7_Washout', 'raw_score': 45.0, 'prev': prev_price, 'target': prev_price, 'ev': MODEL_EV['M7_Washout'], 'cat': 'BPJS'})
                is_m8, m8_plan = self.m8.evaluate(ticker, i_hist)
                if is_m8:
                    report["BPJS"].append({'ticker': ticker, 'model': 'M8_Camarilla', 'raw_score': 40.0, 'prev': prev_price, 'target': m8_plan.get('Target', prev_price), 'ev': MODEL_EV['M8_Camarilla'], 'cat': 'BPJS'})

        # Score them using M9 General
        for cat in report:
            if report[cat]: report[cat] = self.m9.rank_signals(report[cat], regime)

        return report, regime

    def generate_morning_report(self, report, date_str, regime):
        print(f"\n" + "═"*85)
        print(f"🌅 WINTRA MORNING REPORT | {date_str} | REGIME: {regime}")
        print("═"*85)
        
        all_picks = []

        # Print Buckets
        for cat_name, title in [("SWING", "Swing (1-5 Days)"), ("SHORT_SWING", "Short Swing (1-2 Days)"), ("BPJS", "BPJS (Intraday)")]:
            print(f"\n{CYAN}{title}{RESET}")
            if not report[cat_name]:
                print(f"{GRAY}  No signals generated in this bucket.{RESET}")
            else:
                for i, p in enumerate(report[cat_name][:4]):
                    all_picks.append(p)
                    print(f"{i+1}. {p['ticker'].ljust(5)} ({p['final_score']:>4.1f} pts) | Prev: Rp{p['prev']:<6,.0f} | Target: Rp{p['target']:<6,.0f} | EV: {GREEN}{p['ev']}{RESET}")

        # Print Tournament
        print(f"\n🏆 {YELLOW}Wintra Tournament (Top 5 Overall){RESET}")
        print("─"*85)
        all_picks = sorted(all_picks, key=lambda x: x['final_score'], reverse=True)
        for i, p in enumerate(all_picks[:5]):
            print(f"{i+1}. {p['ticker'].ljust(5)} ({p['final_score']:>4.1f} pts) | Prev: Rp{p['prev']:<6,.0f} | Target: Rp{p['target']:<6,.0f} | EV: {GREEN}{p['ev']}{RESET} | {p['model']:<12} | {p['cat']}")
        print("═"*85 + "\n")

if __name__ == "__main__":
    gauntlet = TimeframeGauntlet()
    universe, daily_data, intraday_data = gauntlet.fetch_market_data()
    
    # Identify the start of the "Test Week"
    unique_dates = sorted(list(set(intraday_data.index.date)))
    
    # FIX: Safely pick the oldest available intraday date (which will be ~5 trading days ago)
    if len(unique_dates) >= 1:
        report_date = unique_dates[0] 
        # Generate the formatted report for that morning
        report, regime = gauntlet.evaluate_day(report_date.strftime("%Y-%m-%d"), universe, daily_data, intraday_data)
        
        if report:
            gauntlet.generate_morning_report(report, report_date.strftime("%Y-%m-%d"), regime)
        else:
            print(f"{RED}❌ Could not generate report. Insufficient historical data.{RESET}")
    else:
        print(f"{RED}❌ No intraday data could be fetched from Yahoo Finance at this time.{RESET}")
