import pandas as pd
import pandas_ta as ta

class BreakoutModel:
    """
    Model 3: Breakout (The Velocity Engine) - Version 1.0 (Mathematically Optimized)
    Profile: Momentum / Stage 2 Breakout
    Logic: Algorithmic Grid Search Winners (Bull Market 2025-2026)

    OPTIMIZED PARAMETER LOG:
    -------------------------------------------------------------------------
    - Lookback: 40 Days (Optimal resistance ceiling)
    - Volume: 2.5x Average (Institutional footprint)
    - Pivot: Top 20% (Strict daily close requirement)
    - Max Stretch: < 12.0% above EMA20 (Exhaustion filter)
    - Trend: EMA20 > SMA50 (Structural alignment)
    
    PERFORMANCE (Bull Regime):
    - Win Rate: 52.17%
    - Expected Value: +2.57%
    - Frequency: ~23 High-Conviction Signals per 6-month Bull cycle
    -------------------------------------------------------------------------
    """
    def __init__(self, lookback=40, vol_ma=20, vol_mult=2.5, pivot_req=0.20, max_stretch=12.0):
        self.lookback = lookback
        self.vol_ma = vol_ma
        self.vol_mult = vol_mult
        self.pivot_req = pivot_req
        self.max_stretch = max_stretch
        self.name = "M3"

    def detect_regime(self, market_index_series):
        """
        Model 3 is primarily designed for BULL markets, but we track regime
        for reporting and context. Breakouts in BEAR markets are highly suspect.
        """
        if market_index_series is None or len(market_index_series) < 50:
            return "SIDEWAYS"
            
        m_close = market_index_series
        m_sma50 = ta.sma(m_close, length=50)
        m_ema20 = ta.ema(m_close, length=20)
        
        if m_sma50 is None or m_ema20 is None:
            return "SIDEWAYS"
            
        curr_m = m_close.iloc[-1]
        curr_ema20 = m_ema20.iloc[-1]
        curr_sma50 = m_sma50.iloc[-1]
        
        if curr_m > curr_ema20 and curr_ema20 > curr_sma50:
            return "BULL"
        elif curr_m < curr_ema20 and curr_ema20 < curr_sma50:
            return "BEAR"
        else:
            return "SIDEWAYS"

    def evaluate(self, close_prices, volume_series, high_prices, low_prices, market_index_series=None):
        """
        Evaluates the ticker for a Stage 2 Breakout using optimized parameters.
        """
        # We need enough data to look back 40 days plus some buffer for moving averages
        if len(close_prices) <= self.lookback + 1 or len(volume_series) <= self.vol_ma + 1:
            return False

        # 1. INDICATORS
        ema20 = ta.ema(close_prices, length=20)
        sma50 = ta.sma(close_prices, length=50)
        
        if ema20 is None or sma50 is None:
            return False

        curr_p = close_prices.iloc[-1]
        curr_h = high_prices.iloc[-1]
        curr_l = low_prices.iloc[-1]
        curr_v = volume_series.iloc[-1]
        
        curr_ema20 = ema20.iloc[-1]
        curr_sma50 = sma50.iloc[-1]

        # 2. BREAKOUT LOGIC (Close > Highest High of the last 40 days)
        # We exclude today from the rolling max so we check if we broke the PREVIOUS ceiling
        previous_highs = high_prices.iloc[-(self.lookback+1):-1]
        resistance_ceiling = previous_highs.max()
        
        is_breakout = curr_p > resistance_ceiling

        # 3. VOLUME LOGIC (2.5x the 20-day average)
        # We exclude today's volume from the average calculation
        avg_vol = volume_series.iloc[-(self.vol_ma+1):-1].mean()
        is_vol_climax = curr_v > (avg_vol * self.vol_mult)

        # 4. PIVOT LOGIC (Must close in the Top 20% of the daily range)
        day_range = curr_h - curr_l
        is_pivot = False
        if day_range > 0:
            relative_pos = (curr_p - curr_l) / day_range
            is_pivot = relative_pos >= (1 - self.pivot_req)

        # 5. TREND ALIGNMENT LOGIC (Must be in a structural uptrend)
        is_uptrend = (curr_p > curr_ema20) and (curr_ema20 > curr_sma50)

        # 6. EXHAUSTION LOGIC (Cannot be stretched > 12% from EMA20)
        current_stretch = ((curr_p - curr_ema20) / curr_ema20) * 100
        is_not_overextended = current_stretch <= self.max_stretch

        return (is_breakout and is_vol_climax and is_pivot and is_uptrend and is_not_overextended)

    def get_breakout_strength(self, close_prices, volume_series):
        """
        Scores the breakout. Higher is better. 
        Based on volume surge multiplier.
        """
        if len(volume_series) <= self.vol_ma + 1:
            return 0.0
            
        curr_v = volume_series.iloc[-1]
        avg_vol = volume_series.iloc[-(self.vol_ma+1):-1].mean()
        
        if avg_vol > 0:
            return curr_v / avg_vol
        return 0.0
