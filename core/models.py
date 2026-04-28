import os
import json
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime

class WintraModels:
    """
    The Mathematical Engine for the Wintra Project.
    Executes M1-M4 (Daily) and M5 (Intraday/ARA).
    """
    def __init__(self, data_path="data/idx80_list.json"):
        self.data_path = data_path
        self.universe = self._load_universe()
        # Append .JK for Yahoo Finance routing
        self.yf_tickers = [f"{ticker}.JK" for ticker in self.universe]

    def _load_universe(self):
        """Loads the verified ticker list from the Scraper output."""
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, 'r') as f:
                    data = json.load(f)
                    return data.get('tickers', [])
            except Exception as e:
                print(f"⚠️ Error reading JSON: {e}")
        
        print("🚨 CRITICAL: Scraper data missing. Using empty universe.")
        return []

    def fetch_daily_data(self, period="60d"):
        """Fetches end-of-day data for Models 1-4."""
        print(f"📡 Fetching {period} daily data for {len(self.yf_tickers)} tickers...")
        # 🔧 FIRM FIX: threads=False prevents SQLite database locking
        data = yf.download(self.yf_tickers, period=period, interval="1d", threads=False, progress=False)
        return data['Close'], data['Volume']

    def fetch_intraday_data(self):
        """Fetches live 1-minute data for Model 5 (ARA Forecaster) VWAP calculations."""
        print("📡 Fetching intraday data for ARA Forecaster...")
        # 🔧 FIRM FIX: threads=False ensures absolute data integrity
        data = yf.download(self.yf_tickers, period="1d", interval="1m", threads=False, progress=False)
        return data

    def run_daily_tournament(self, prices, volumes):
        """
        Executes Models 1 through 4.
        Returns a list of dictionaries containing scores and signals.
        """
        print("⚔️ Running M1-M4 Daily Tournament...")
        results = []

        for ticker in self.yf_tickers:
            try:
                # Forward fill to handle any isolated missing days
                close = prices[ticker].ffill()
                vol = volumes[ticker].ffill()
                current_price = close.iloc[-1]
                
                if pd.isna(current_price):
                    continue

                score = 0
                signals = []

                # --- M1: TREND (Momentum Alignment) ---
                ema20 = ta.ema(close, length=20)
                sma50 = ta.sma(close, length=50)
                if current_price > ema20.iloc[-1] and current_price > sma50.iloc[-1]:
                    score += 1.0
                    signals.append('M1')

                # --- M2: REVERSION (Oversold Bounce) ---
                rsi = ta.rsi(close, length=14)
                if rsi.iloc[-1] < 35:
                    score += 1.0
                    signals.append('M2')

                # --- M3: INSTITUTIONAL (Volume Anomaly) ---
                vol_20d_avg = ta.sma(vol, length=20)
                if vol.iloc[-1] > (vol_20d_avg.iloc[-1] * 1.5):
                    score += 1.5
                    signals.append('M3')

                # --- M4: MACRO PROXY (Relative Strength) ---
                pct_change_5d = (current_price - close.iloc[-5]) / close.iloc[-5]
                if pct_change_5d > 0.02:
                    score += 1.2
                    signals.append('M4')

                if score > 0:
                    char = "Powerhouse" if score >= 3 else "Specialist" if score >= 2 else "Wildcard"
                    results.append({
                        'ticker': ticker.replace('.JK', ''),
                        'price': float(current_price),
                        'score': float(score),
                        'signals': ", ".join(signals),
                        'char': char
                    })
            except Exception:
                # Skip silently if a stock was suspended or lacks data
                pass

        # Sort by highest score first
        return sorted(results, key=lambda x: x['score'], reverse=True)

    def run_ara_forecaster(self, daily_volumes, intraday_data, elapsed_minutes=50):
        """
        Executes Model 5: Intraday Volume Velocity (RVV) and VWAP Breakout.
        Designed specifically for the 09:50 AM Audit.
        """
        print("🚨 Running M5 ARA Forecaster...")
        results = []
        
        intra_close = intraday_data['Close']
        intra_high = intraday_data['High']
        intra_low = intraday_data['Low']
        intra_vol = intraday_data['Volume']

        for ticker in self.yf_tickers:
            try:
                # 1. Calculate the 20-day historical average volume
                vol_history = daily_volumes[ticker].ffill()
                avg_vol_20d = ta.sma(vol_history, length=20).iloc[-2] # Use yesterday's average
                
                # 2. Extract today's intraday profile
                current_price = intra_close[ticker].dropna().iloc[-1]
                open_price = intra_close[ticker].dropna().iloc[0]
                current_vol = intra_vol[ticker].dropna().sum()
                
                # 3. Calculate Intraday VWAP
                # Typical Price = (High + Low + Close) / 3
                typical_price = (intra_high[ticker] + intra_low[ticker] + intra_close[ticker]) / 3
                vwap = (typical_price * intra_vol[ticker]).sum() / current_vol

                # 4. Calculate RVV (Relative Volume Velocity)
                # Formula: (Current Vol / 20d Avg Vol) * (Total Mins / Elapsed Mins)
                # Assuming 360 minutes in a full IDX trading day
                rvv = (current_vol / avg_vol_20d) * (360 / elapsed_minutes)
                
                # 5. Price % Change from Open
                pct_from_open = (current_price - open_price) / open_price

                # --- M5 FIRM TRIGGERS ---
                if rvv > 3.0 and current_price > vwap and pct_from_open > 0.03:
                    results.append({
                        'ticker': ticker.replace('.JK', ''),
                        'price': float(current_price),
                        'vwap': float(vwap),
                        'rvv': float(rvv),
                        'pct_up': float(pct_from_open * 100),
                        'status': 'ARA ALERT TRIGGERED'
                    })
            except Exception:
                pass
                
        return sorted(results, key=lambda x: x['rvv'], reverse=True)

if __name__ == "__main__":
    # Quick Local Test
    engine = WintraModels()
    d_close, d_vol = engine.fetch_daily_data()
    top_picks = engine.run_daily_tournament(d_close, d_vol)
    print(f"Daily Tournament Complete. Found {len(top_picks)} candidates with scores > 0.")