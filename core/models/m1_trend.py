import pandas as pd
import numpy as np

class TrendModel:
    """
    Model 1: Trend Following & Breakout (Simplified - Daily Only)
    Logic: Focuses on institutional accumulation and macro-trend health.
    """
    def __init__(self):
        self.name = "M1_Trend_Following"
        
        # Strategy Parameters (Daily Timeframe)
        self.ma_fast = 20        # Momentum period
        self.ma_med = 50         # Mid-term trend
        self.ma_slow = 200       # Long-term macro filter
        self.lookback_high = 20   # Resistance period for breakout
        self.vol_multiplier = 1.5 # 150% volume spike requirement

    def analyze(self, df, target_date=None):
        """
        Analyzes daily OHLCV data to determine trend-following buy signals.
        """
        # 1. Validation: Ensure minimum data for 200-day SMA calculation
        if df.empty or len(df) < self.ma_slow:
            return False

        # Sort chronologically to ensure rolling calculations are correct
        df = df.sort_values(by='Datetime').reset_index(drop=True)

        # 2. Indicator Calculation
        # Moving Averages
        df['SMA_20'] = df['Close'].rolling(window=self.ma_fast).mean()
        df['SMA_50'] = df['Close'].rolling(window=self.ma_med).mean()
        df['SMA_200'] = df['Close'].rolling(window=self.ma_slow).mean()
        
        # Volume Average
        df['Vol_20_Avg'] = df['Volume'].rolling(window=self.ma_fast).mean()
        
        # Resistance Level (Highest high of the last 20 days, excluding current candle)
        df['20D_High'] = df['High'].shift(1).rolling(window=self.lookback_high).max()

        # 3. Locate Analysis Point
        if target_date:
            # Match date regardless of time/timezone formatting
            df['Date_Str'] = pd.to_datetime(df['Datetime']).dt.strftime('%Y-%m-%d')
            current_data = df[df['Date_Str'] == target_date]
            if current_data.empty:
                return False
            current_row = current_data.iloc[-1]
        else:
            current_row = df.iloc[-1]

        # Prevent logic execution on incomplete data (warm-up phase)
        if pd.isna(current_row['SMA_200']) or pd.isna(current_row['20D_High']):
            return False

        # 4. --- M1 STRATEGY LOGIC ---
        
        # Condition 1: Macro Trend (Price must be above 50 and 200 SMA)
        # This filters out "dead" stocks and focuses on active leaders.
        is_bullish = (current_row['Close'] > current_row['SMA_50']) and \
                     (current_row['Close'] > current_row['SMA_200'])

        # Condition 2: Price Breakout
        # Current Close is higher than any price in the last 20 trading days.
        is_breakout = current_row['Close'] > current_row['20D_High']

        # Condition 3: Volume Confirmation
        # High volume indicates the move has "legs" and institutional backing.
        is_high_vol = current_row['Volume'] > (current_row['Vol_20_Avg'] * self.vol_multiplier)

        # 5. Result
        return bool(is_bullish and is_breakout and is_high_vol)

if __name__ == "__main__":
    print("[*] M1 Trend Model (Daily Baseline) Initialized.")
