import os
import json
import io
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import sys

# 1. IMPORT WINTRA CORE INFRASTRUCTURE (Synced with Repository Clean State)
from core.data_gate import DataGate
from core.models.m1_trend import TrendModel as M1
from core.models.m2_revert import RevertModel as M2
from core.models.m3_breakout import BreakoutModel as M3
from core.models.m4_leadership import LeadershipModel as M4
from core.models.m9_controller import PortfolioController as M9

# ANSI Colors for Windows-compatible terminal output
CYAN, GREEN, YELLOW, RED, MAGENTA, GRAY, RESET = "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[95m", "\033[90m", "\033[0m"

class WintraSwingTest:
    def __init__(self):
        # Initialize the production models
        self.m1 = M1()
        self.m2 = M2()
        self.m3 = M3()
        self.m4 = M4()
        
        # M9 CONFIGURATION:
        # max_slots=4: Sets the total portfolio size to 4.
        # max_per_model=4: Allows the tournament to pick 4 stocks from the same engine 
        # if they are the strongest candidates available.
        self.m9 = M9(max_slots=4, max_per_model=4)
        
        # We use the training cache for historical accuracy on specific dates
        self.cache_file = os.path.join("core", "data", "m2_training_cache.json")

    def load_test_data(self):
        """Loads historical daily data from the Wintra Training Cache."""
        if not os.path.exists(self.cache_file):
            print(f"{RED}[ERROR] Training cache (m2_training_cache.json) missing.{RESET}")
            sys.exit(1)
            
        with open(self.cache_file, 'r') as f:
            cache = json.load(f)
            
        ihsg = pd.read_json(io.StringIO(cache['ihsg']))
        ihsg.index = pd.to_datetime(ihsg.index)
        
        universe_data = {}
        for ticker, df_json in cache['tickers'].items():
            df = pd.read_json(io.StringIO(df_json))
            df.index = pd.to_datetime(df.index)
            universe_data[ticker] = df
            
        return universe_data, ihsg

    def run_morning_evaluation(self, target_date_str):
        target_dt = pd.to_datetime(target_date_str)
        universe_data, ihsg_data = self.load_test_data()
        
        # 1. Macro Context (Data up to the morning of the test)
        ihsg_morning = ihsg_data.loc[ihsg_data.index < target_dt]['Close']
        if ihsg_morning.empty:
            print(f"{RED}[ERROR] No IHSG data found before {target_date_str}{RESET}")
            return
            
        regime = self.m1.detect_regime(ihsg_morning)
        raw_signals = []

        # 2. Scanning Universe with Synced Signatures
        for ticker, df in universe_data.items():
            morning_data = df.loc[df.index < target_dt]
            if len(morning_data) < 55: continue
            
            # Extract standard OHLCV series
            c, v, o, h, l = morning_data['Close'], morning_data['Volume'], morning_data['Open'], morning_data['High'], morning_data['Low']
            
            # --- MODEL 1: TREND (Ignition) ---
            if self.m1.evaluate(close_prices=c, volume_series=v, market_index_series=ihsg_morning):
                raw_signals.append({
                    'ticker': ticker, 'model': 'M1', 
                    'raw_score': max(0, 100 - (self.m1.get_proximity(c)*10)),
                    'desc': 'Trend Ignition'
                })
            
            # --- MODEL 2: REVERT (Sniper) ---
            if self.m2.evaluate(close_prices=c, volume_series=v, open_prices=o, high_prices=h, low_prices=l, market_index_series=ihsg_morning):
                raw_signals.append({
                    'ticker': ticker, 'model': 'M2', 
                    'raw_score': self.m2.get_elasticity_score(c) * 12,
                    'desc': 'Mean Reversion'
                })

            # --- MODEL 3: BREAKOUT (Velocity) ---
            if self.m3.evaluate(close_prices=c, volume_series=v, high_prices=h, low_prices=l, market_index_series=ihsg_morning):
                raw_signals.append({
                    'ticker': ticker, 'model': 'M3', 
                    'raw_score': self.m3.get_breakout_strength(c, v) * 20,
                    'desc': 'Stage 2 Breakout'
                })

            # --- MODEL 4: LEADERSHIP (Alpha) ---
            if self.m4.evaluate(close_prices=c, volume_series=v, open_prices=o, high_prices=h, market_index_series=ihsg_morning):
                raw_signals.append({
                    'ticker': ticker, 'model': 'M4', 
                    'raw_score': self.m4.get_alpha_score(c, ihsg_morning) * 10,
                    'desc': 'Alpha Leader'
                })

        # 3. TOURNAMENT RANKING (M9 General Logic)
        ranked_picks = self.m9.rank_signals(raw_signals, regime)
        final_picks = self.m9.manage_exposure({}, ranked_picks)

        # 4. OUTPUT REPORT
        print(f"\n" + "═"*85)
        print(f"{CYAN}[WINTRA SWING BUCKET REPORT]{RESET}")
        print(f"Target Date : {target_date_str} | 08:30 WIB")
        print(f"Market State: {MAGENTA}{regime}{RESET}")
        print("═"*85)
        
        if not final_picks:
            print(f"{YELLOW}No stocks met the conviction threshold for this morning.{RESET}")
        else:
            print(f"{'Rank':<5} | {'Ticker':<8} | {'Score':<8} | {'Engine':<10} | {'Strategy'}")
            print("─"*85)
            # Display exactly Top 4
            for i, p in enumerate(final_picks[:4]):
                print(f" {i+1:<4} | {GREEN}{p['ticker']:<8}{RESET} | {p['final_score']:>6.1f} | {p['model']:<10} | {p['desc']}")
        
        print("═"*85 + "\n")

if __name__ == "__main__":
    # --- GATE 2: DAILY VALIDATION ---
    DataGate.verify(mode="daily", force_sync=False)

    # Start Simulation for April 27, 2026
    tester = WintraSwingTest()
    tester.run_morning_evaluation("2026-04-27")