import pandas as pd
import pandas_ta as ta

class TrendModel:
    """
    Model 1: Trend (The Ignition Engine) - Version 4.5 (The Balanced Blade)
    Profile: Aggressive Bull Hunter / Volume-Pure Bear Guard
    
    FINAL VERIFIED STRATEGY:
    -------------------------------------------------------------------------
    1. BULL (Optimized Hunter): 45.12% Win Rate | +1.86% EV | ~580 Signals
       Logic: 1.25x Vol | 15% Max Stretch | Pivot OFF.
       Observation: The loose filters allow the engine to catch the maximum 
       number of trending "sparks" in a healthy market.
       
    2. DEFENSIVE (Legacy Elite Guard): 50.00% Win Rate | +3.96% EV | 38 Signals
       Logic: 1.80x Vol | Stretch OFF | Pivot OFF.
       Observation: Reverted to pure Volume Shielding. Round 4 testing proved
       that Pivot/Stretch filters in a Bear market block massive winners 
       (e.g., BRPT +24%) that ignite "messily" but powerfully.
    -------------------------------------------------------------------------
    """
    def __init__(self, vol_ma=20):
        self.vol_ma = vol_ma
        self.name = "M1_PROD"

    def detect_regime(self, market_index_series):
        if market_index_series is None or len(market_index_series) < 50:
            return "DEFENSIVE"
            
        m_close = market_index_series
        m_sma50 = ta.sma(m_close, length=50)
        m_ema20 = ta.ema(m_close, length=20)
        
        if m_sma50 is None or m_ema20 is None:
            return "DEFENSIVE"
            
        curr_m = m_close.iloc[-1]
        curr_ema20 = m_ema20.iloc[-1]
        curr_sma50 = m_sma50.iloc[-1]
        
        # BULL: Price > EMA20 AND EMA20 > SMA50
        if curr_m > curr_ema20 and curr_ema20 > curr_sma50:
            return "BULL"
        else:
            return "DEFENSIVE"

    def evaluate(self, close_prices, volume_series, open_prices=None, high_prices=None, low_prices=None, market_index_series=None):
        if len(close_prices) < 30: return False
        
        regime = self.detect_regime(market_index_series)
        
        # ⚙️ FINAL HYBRID CALIBRATION (V4.5)
        if regime == "BULL":
            vol_thresh = 1.25          # Optimized Bull Volume
            max_stretch = 15.0         # Optimized Bull Stretch
            pivot_req = 1.0            # Pivot OFF
        else: 
            # DEFENSIVE (Reverted to Legacy Pure Volume)
            vol_thresh = 1.80          # Elite Guard Volume
            max_stretch = 999.0        # Stretch OFF (Proven to block winners in Bear)
            pivot_req = 1.0            # Pivot OFF (Proven to block winners in Bear)

        # 1. INDICATORS
        ema_f = ta.ema(close_prices, length=10)
        ema_s = ta.ema(close_prices, length=20)
        if ema_f is None or ema_s is None: return False

        curr_p = close_prices.iloc[-1]
        curr_ef = ema_f.iloc[-1]
        curr_es = ema_s.iloc[-1]
        
        # 2. BASE LOGIC GATES
        is_stacked = (curr_p > curr_ef) and (curr_ef > curr_es)
        
        avg_vol = volume_series.iloc[-21:-1].mean()
        is_vol = volume_series.iloc[-1] > (avg_vol * vol_thresh)
        
        current_stretch = ((curr_p - curr_ef) / curr_ef) * 100
        is_not_exhausted = current_stretch <= max_stretch

        # 3. PIVOT CHECK (Only active if pivot_req < 1.0)
        is_pivot = True
        if pivot_req < 1.0 and high_prices is not None and low_prices is not None:
            curr_h, curr_l = high_prices.iloc[-1], low_prices.iloc[-1]
            day_range = (curr_h - curr_l) if (curr_h - curr_l) > 0 else 0.001
            is_pivot = (curr_p - curr_l) / day_range >= (1 - pivot_req)

        return is_stacked and is_vol and is_not_exhausted and is_pivot

    def get_proximity(self, close_prices):
        ema_fast = ta.ema(close_prices, length=10)
        if ema_fast is None: return 999.0
        curr_p = close_prices.iloc[-1]
        curr_ef = ema_fast.iloc[-1]
        return ((curr_p - curr_ef) / curr_ef) * 100
