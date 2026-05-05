import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import pandas_ta as ta
import inspect
import sys

# 1. IMPORT DATA GATE & PRODUCTION ENGINES
from core.data_gate import DataGate
from core.models.m1_trend import TrendModel as M1
from core.models.m3_breakout import BreakoutModel as M3
from core.models.m4_leadership import LeadershipModel as M4
from core.models.m9_controller import PortfolioController as M9

# ANSI Colors
CYAN, GREEN, YELLOW, RED, MAGENTA, GRAY, RESET = "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[95m", "\033[90m", "\033[0m"

# Hardcoded Historical EV for Display
MODEL_EV = {"M1_Trend": "+1.86%", "M3_Breakout": "+2.57%", "M4_Alpha": "+2.41%"}
SWING_STOP_LOSS = -3.5 # 3.5% wide stop for 1-5 day swings

class SwingSimulator:
    def __init__(self):
        self.m1 = M1()
        self.m3 = M3()
        self.m4 = M4()
        self.m9 = M9()

    def fetch_market_data(self):
        """
        Fetches daily data for the simulation. 
        Note: The DataGate ensures the environment is fresh before this runs.
        """
        print(f"{GRAY}📡 Fetching Daily Data for 70-day Swing Analysis...{RESET}")
        list_path = os.path.join("core", "data", "idx80_list.json")
        if os.path.exists(list_path):
            with open(list_path, 'r') as f: universe = json.load(f).get('tickers', [])
        else:
            universe = ["BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ASII", "GOTO", "AMMN", "BREN", "SIDO", "MEDC", "ADRO", "PTBA"]
            
        yf_tickers = [f"{t}.JK" for t in universe]
        
        # We download daily data here for the longer lookbacks (SMA50) required by swing models
        daily_data = yf.download(yf_tickers + ["^JKSE"], period="70d", interval="1d", progress=False)
        
        if daily_data.index.tz is not None: 
            daily_data.index = daily_data.index.tz_localize(None)
            
        return universe, daily_data

    def evaluate_morning(self, date_dt, universe, daily_data):
        ihsg_hist = daily_data['Close']["^JKSE"].loc[daily_data.index <= date_dt]
        if len(ihsg_hist) < 50: return None, None, None
        
        regime = self.m1.detect_regime(ihsg_hist)
        report = []
        
        diagnostics = {
            "total_scanned": len(universe),
            "valid_data": 0,
            "raw_m1": 0,
            "raw_m3": 0,
            "raw_m4": 0,
            "m1_near_misses": [],
            "m3_near_misses": [],
            "m4_near_misses": [],
            "ghost_rejections": []
        }
        
        for ticker in universe:
            sym = f"{ticker}.JK"
            if sym not in daily_data['Close']: continue
            
            d_hist = pd.DataFrame({
                'Open': daily_data['Open'][sym], 'High': daily_data['High'][sym],
                'Low': daily_data['Low'][sym], 'Close': daily_data['Close'][sym], 'Volume': daily_data['Volume'][sym]
            }).loc[daily_data.index <= date_dt].dropna()
            
            if len(d_hist) < 50: continue
            diagnostics["valid_data"] += 1
            
            c, v, o, h, l = d_hist['Close'], d_hist['Volume'], d_hist['Open'], d_hist['High'], d_hist['Low']
            
            try:
                atr_series = ta.atr(h, l, c, length=14)
                atr = atr_series.iloc[-1] if atr_series is not None else (c.iloc[-1] * 0.02)
            except:
                atr = c.iloc[-1] * 0.02
                
            prev_price = c.iloc[-1]
            
            # --- MODEL EVALUATIONS ---
            # M1 Trend
            if self.m1.evaluate(close_prices=c, volume_series=v, market_index_series=ihsg_hist):
                diagnostics["raw_m1"] += 1
                try: prox = self.m1.get_proximity(c)
                except: prox = 5.0
                report.append({'ticker': ticker, 'model': 'M1_Trend', 'raw_score': max(0, 100 - (prox * 5)), 'prev': prev_price, 'target': prev_price + (atr*2), 'ev': MODEL_EV['M1_Trend']})

            # M3 Breakout
            if self.m3.evaluate(close_prices=c, volume_series=v, high_prices=h, low_prices=l, market_index_series=ihsg_hist):
                diagnostics["raw_m3"] += 1
                try: str_score = self.m3.get_breakout_strength(c, v)
                except: str_score = 1.0
                report.append({'ticker': ticker, 'model': 'M3_Breakout', 'raw_score': str_score * 25, 'prev': prev_price, 'target': prev_price + (atr*3), 'ev': MODEL_EV['M3_Breakout']})

            # M4 Leadership
            if self.m4.evaluate(close_prices=c, volume_series=v, open_prices=o, high_prices=h, market_index_series=ihsg_hist):
                diagnostics["raw_m4"] += 1
                alpha_score = self.m4.get_alpha_score(c, ihsg_hist) if hasattr(self.m4, 'get_alpha_score') else 1.0
                report.append({'ticker': ticker, 'model': 'M4_Alpha', 'raw_score': max(0, alpha_score * 10), 'prev': prev_price, 'target': prev_price + (atr*2.5), 'ev': MODEL_EV['M4_Alpha']})

        ranked_report = self.m9.rank_signals(report, regime) if report else []
        return ranked_report, regime, diagnostics

    def simulate_forward_performance(self, ticker, entry_date, daily_data):
        sym = f"{ticker}.JK"
        future_data = daily_data.loc[daily_data.index > entry_date]
        if sym not in future_data.columns.levels[1] if isinstance(future_data.columns, pd.MultiIndex) else sym not in future_data:
            return None
            
        future_df = pd.DataFrame({
            'High': daily_data['High'][sym], 'Low': daily_data['Low'][sym], 'Close': daily_data['Close'][sym]
        }).loc[daily_data.index > entry_date].dropna().head(5)
        
        if future_df.empty: return None
        
        entry_price = daily_data['Close'][sym].loc[daily_data.index <= entry_date].dropna().iloc[-1]
        
        max_high = future_df['High'].max()
        min_low = future_df['Low'].min()
        final_close = future_df['Close'].iloc[-1]
        
        max_gain = ((max_high - entry_price) / entry_price) * 100
        max_drawdown = ((min_low - entry_price) / entry_price) * 100
        
        if max_drawdown <= SWING_STOP_LOSS:
            return {"max_gain": max_gain, "max_drawdown": max_drawdown, "final_return": SWING_STOP_LOSS, "status": f"{RED}STOPPED OUT{RESET}", "days_tracked": len(future_df)}
        else:
            final_return = ((final_close - entry_price) / entry_price) * 100
            return {"max_gain": max_gain, "max_drawdown": max_drawdown, "final_return": final_return, "status": f"{GREEN}HELD{RESET}" if final_return > 0 else f"{YELLOW}HELD{RESET}", "days_tracked": len(future_df)}

if __name__ == "__main__":
    # --- GATE 2: DAILY VALIDATION GATE ---
    # This will trigger scraper.py and verify if T-1 data is present.
    # If the gate fails, sys.exit(1) is called internally.
    DataGate.verify(mode="daily", force_sync=True)

    # Proceed only if Gate is Open
    sim = SwingSimulator()
    universe, daily_data = sim.fetch_market_data()
    unique_dates = daily_data.dropna(subset=[('Close', '^JKSE')]).index.unique().sort_values()
    
    if len(unique_dates) >= 6:
        # We target a window from 5 trading days ago to simulate a full T+5 week
        target_date = unique_dates[-6]
        date_str = target_date.strftime("%Y-%m-%d")
        
        report, regime, diag = sim.evaluate_morning(target_date, universe, daily_data)
        
        print(f"\n" + "═"*85)
        print(f"🌅 WINTRA SWING BUCKET REPORT | {date_str} | REGIME: {regime}")
        print("═"*85)
        
        if not report:
            print(f"\n{GRAY}  No SWING signals generated for this date.{RESET}")
        else:
            print(f"\n🏆 {CYAN}Swing Tournament (Top 5 Candidates){RESET}")
            print("─"*85)
            for i, p in enumerate(report[:5]):
                print(f"{i+1}. {p['ticker'].ljust(5)} ({p['final_score']:>5.1f} pts) | Prev: Rp{p['prev']:<6,.0f} | Target: Rp{p['target']:<6,.0f} | EV: {GREEN}{p['ev']}{RESET} | {p['model']}")
            
            print(f"\n📈 {MAGENTA}5-DAY FORWARD PERFORMANCE GAUNTLET (T+1 to T+5){RESET}")
            print("─"*85)
            print(f"{'Ticker':<6} | {'Max Peak':<10} | {'Max Drawdown':<15} | {'Final Return':<13} | {'Status'}")
            print("─"*85)
            
            for p in report[:5]:
                perf = sim.simulate_forward_performance(p['ticker'], target_date, daily_data)
                if perf:
                    peak_str = f"{GREEN}{perf['max_gain']:>+6.2f}%{RESET}" if perf['max_gain'] > 0 else f"{GRAY}{perf['max_gain']:>+6.2f}%{RESET}"
                    dd_str = f"{RED}{perf['max_drawdown']:>+6.2f}%{RESET}" if perf['max_drawdown'] < 0 else f"{GRAY}{perf['max_drawdown']:>+6.2f}%{RESET}"
                    ret_str = f"{GREEN if perf['final_return'] > 0 else RED}{perf['final_return']:>+6.2f}%{RESET}"
                    print(f"{p['ticker']:<6} | {peak_str:<19} | {dd_str:<24} | {ret_str:<22} | {perf['status']} ({perf['days_tracked']}d)")
                    
        print("═"*85 + "\n")
    else:
        print(f"{RED}❌ Insufficient historical data to run a 5-day backward anchor.{RESET}")