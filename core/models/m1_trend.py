import pandas as pd
import pandas_ta as ta

class TrendModel:
    """
    Model 1: Trend (The Ignition Engine) - Version 2.0 (Adaptive Edition)
    Profile: Aggressive but Regime-Aware
    
    PERSONALITY LOG (Training Results):
    -------------------------------------------------------------------------
    1. SIDEWAYS (The Alpha Hunter): BEST WINRATE (71.88%)
       Nature: Hunter. Thrives on individual stock strength when the index is boring.
       
    2. CRASH (The Elite Guard): BEST EXPECTED VALUE (EV +5.62%)
       Nature: Guard. Extremely selective. Stays in cash for most of the crash, 
       only allowing 'Unicorn' anomalies to pass.
       
    3. BULL (The Disciplined Sniper): NEUTRAL/CONSISTENT (50.00% WR)
       Nature: Sniper. Focuses on quality breakouts during hot markets to avoid 
       over-extension and fakeouts.
    -------------------------------------------------------------------------
    """
    def __init__(self, fast_ema=10, slow_ema=20, vol_ma=20):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.vol_ma = vol_ma
        self.name = "M1"

    def detect_regime(self, market_index_series):
        """
        Detects the current market environment.
        Returns: 'BULL', 'SIDEWAYS', or 'BEAR'
        """
        if market_index_series is None or len(market_index_series) < 50:
            return "SIDEWAYS" # Default safety
            
        m_close = market_index_series
        m_sma50 = ta.sma(m_close, length=50)
        m_ema20 = ta.ema(m_close, length=20)
        
        curr_m = m_close.iloc[-1]
        curr_ema20 = m_ema20.iloc[-1]
        curr_sma50 = m_sma50.iloc[-1]
        
        # 📈 BULL: Index above EMA20 and EMA20 above SMA50
        if curr_m > curr_ema20 and curr_ema20 > curr_sma50:
            return "BULL"
        # 📉 BEAR: Index below EMA20 and EMA20 below SMA50
        elif curr_m < curr_ema20 and curr_ema20 < curr_sma50:
            return "BEAR"
        # ↔️ SIDEWAYS: Caught in between
        else:
            return "SIDEWAYS"

    def evaluate(self, close_prices, volume_series, market_index_series=None):
        """
        Evaluates ticker with dynamic thresholds based on detected regime.
        """
        if len(close_prices) < 30 or len(volume_series) < self.vol_ma:
            return False

        regime = self.detect_regime(market_index_series)
        
        # ⚙️ DYNAMIC PARAMETER ASSIGNMENT (THE NATURES)
        if regime == "BULL":
            vol_thresh = 1.25
            rsi_min, rsi_max = 50, 85
        elif regime == "BEAR":
            vol_thresh = 1.80  # The 'Guard' requires massive institutional volume
            rsi_min, rsi_max = 40, 55 # Focus on early recovery momentum
        else: # SIDEWAYS
            vol_thresh = 1.45
            rsi_min, rsi_max = 50, 65 # The 'Hunter' demands tight quality control

        # 1. PRICE & MOMENTUM
        ema_fast = ta.ema(close_prices, length=self.fast_ema)
        ema_slow = ta.ema(close_prices, length=self.slow_ema)
        rsi = ta.rsi(close_prices, length=14)
        
        if ema_fast is None or ema_slow is None or rsi is None:
            return False

        curr_p = close_prices.iloc[-1]
        curr_ef = ema_fast.iloc[-1]
        curr_es = ema_slow.iloc[-1]
        curr_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]

        # 2. LOGIC GATES
        is_stacked = curr_p > curr_ef and curr_ef > curr_es
        is_momentum_fresh = rsi_min < curr_rsi < rsi_max and curr_rsi > prev_rsi
        
        avg_vol = volume_series.iloc[-(self.vol_ma+1):-1].mean()
        curr_vol = volume_series.iloc[-1]
        is_vol_confirmed = curr_vol > (avg_vol * vol_thresh)

        return is_stacked and is_momentum_fresh and is_vol_confirmed

    def get_proximity(self, close_prices):
        ema_fast = ta.ema(close_prices, length=self.fast_ema)
        if ema_fast is None: return 999.0
        curr_p = close_prices.iloc[-1]
        curr_ef = ema_fast.iloc[-1]
        return ((curr_p - curr_ef) / curr_ef) * 100
