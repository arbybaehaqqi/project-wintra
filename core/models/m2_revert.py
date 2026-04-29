import pandas as pd
import pandas_ta as ta
import numpy as np

class RevertModel:
    """
    Model 2: Revert (The Elasticity Engine) - Version 3.7 (The Bull Sniper Upgrade)
    Profile: Contrarian / Mean Reversion
    Logic: Elasticity Stretch + EMA Slope (Bull Fix) + Strict Green Absorption.

    PERSONALITY LOG (Training Results):
    -------------------------------------------------------------------------
    1. SIDEWAYS (The Range Master): LOCKED (EV +3.27% / WR 66.7%)
       Nature: Hunter. High-precision performance in range-bound markets.
       
    2. CRASH (The Capitulation Shield): LOCKED (EV +1.65% / WR 57.1%)
       Nature: Guard. Effectively filtering Dead Cat Bounces via the Green Gate.
       
    3. BULL (The Bull Sniper): THE FINAL WIN-RATE FIX (Targeting 50%+)
       Nature: Sniper. Tightened Bull Elasticity (6.0%) and Pivot (25%).
       Now demands extreme 'V-Rejection' to filter out trend reversals.
    -------------------------------------------------------------------------
    """
    def __init__(self, ema_period=20, rsi_period=7, bb_std=2.0):
        self.ema_period = ema_period
        self.rsi_period = rsi_period
        self.bb_std = bb_std
        self.name = "M2"

    def detect_regime(self, market_index_series):
        """
        Detects market environment for adaptive parameter switching.
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

    def evaluate(self, close_prices, volume_series, open_prices=None, low_prices=None, high_prices=None, market_index_series=None):
        """
        Evaluates 'Stretch' using Version 3.7 logic:
        - Bull: Stricter pivot (0.25) and stretch (6.0%) to fix win rate.
        - Bear: Preservation of V3.6 success (7.5% stretch / 0.33 pivot).
        - Sideways: Preservation of V3.6 success (5.0% stretch / 0.50 pivot).
        """
        if len(close_prices) < 30:
            return False

        regime = self.detect_regime(market_index_series)
        
        # ⚙️ DYNAMIC PARAMETERS: Version 3.7 Calibration
        if regime == "BULL":
            # Quality Filter: Targetting higher win rate in uptrends
            rsi_threshold = 26 # Stricter (Must be more washed out)
            elasticity_req = 6.0 # Increased from 5.5% (Must be a significant puke)
            vol_climax_req = 1.50 # High volume required for the 'Buy the Dip' crowd
            pivot_req = 0.25 # Top 25% (Extreme reclaim required)
            force_green = True
            check_slope = True 
        elif regime == "BEAR":
            # PRESERVING SUCCESSFUL CRASH SHIELD (EV +1.65%)
            rsi_threshold = 28 
            elasticity_req = 7.5 
            vol_climax_req = 1.45 
            pivot_req = 0.33 
            force_green = True
            check_slope = False 
        else: # SIDEWAYS
            # PRESERVING RANGE MASTER (EV +3.27%)
            rsi_threshold = 30
            elasticity_req = 5.0
            vol_climax_req = 1.3
            pivot_req = 0.5
            force_green = False
            check_slope = False

        # 1. INDICATORS
        ema20 = ta.ema(close_prices, length=self.ema_period)
        bbands = ta.bbands(close_prices, length=self.ema_period, std=self.bb_std)
        rsi = ta.rsi(close_prices, length=self.rsi_period)
        
        if ema20 is None or bbands is None or rsi is None:
            return False

        curr_p = close_prices.iloc[-1]
        prev_p = close_prices.iloc[-2]
        curr_o = open_prices.iloc[-1] if open_prices is not None else curr_p
        
        curr_ema20 = ema20.iloc[-1]
        curr_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]
        
        lower_band_col = [col for col in bbands.columns if col.startswith('BBL_')]
        if not lower_band_col:
            return False
        lower_band = bbands[lower_band_col[0]].iloc[-1]
        
        # 2. THE SNAP-BACK LOGIC
        stretch = ((curr_ema20 - curr_p) / curr_ema20) * 100
        is_stretched = stretch > elasticity_req
        
        # Buffer tolerance
        floor_buffer = 1.012 if regime == "BEAR" else 1.020
        is_at_floor = curr_p <= (lower_band * floor_buffer) 
        is_exhausted = curr_rsi < rsi_threshold

        # 3. SLOPE CHECK (The Bull Fix)
        is_slope_ok = True
        if check_slope and len(ema20) >= 5:
            # Check if EMA20 is trending up (structural health)
            slope = ema20.iloc[-1] - ema20.iloc[-5]
            if slope <= 0: 
                is_slope_ok = False

        # 4. MOMENTUM HOOK
        is_hooked = (curr_rsi > prev_rsi)

        # 5. PIVOT & GREEN GATE (Absorption Confirmation)
        is_confirmed = False
        if low_prices is not None and high_prices is not None:
            curr_l = low_prices.iloc[-1]
            curr_h = high_prices.iloc[-1]
            day_range = curr_h - curr_l
            
            if day_range > 0:
                relative_pos = (curr_p - curr_l) / day_range
                is_pivot = relative_pos >= (1 - pivot_req)
                is_green = curr_p > curr_o
                
                if force_green:
                    is_confirmed = is_pivot and is_green
                else:
                    is_confirmed = is_pivot
        else:
            is_confirmed = True

        # 🧪 EXHAUSTION OVERRIDE: RSI < 10 is absolute capitulation
        if curr_rsi < 10:
            is_hooked = True
            is_confirmed = True
            is_slope_ok = True

        # 6. VOLUME CLIMAX
        avg_vol = volume_series.iloc[-21:-1].mean()
        curr_vol = volume_series.iloc[-1]
        is_volume_climax = curr_vol > (avg_vol * vol_climax_req)

        return (is_stretched and is_at_floor and is_exhausted and 
                is_slope_ok and is_confirmed and is_volume_climax and is_hooked)

    def get_elasticity_score(self, close_prices):
        """
        Higher score = more stretched rubber band.
        """
        ema20 = ta.ema(close_prices, length=self.ema_period)
        if ema20 is None: return 0.0
        curr_p = close_prices.iloc[-1]
        curr_ema = ema20.iloc[-1]
        return ((curr_ema - curr_p) / curr_ema) * 100