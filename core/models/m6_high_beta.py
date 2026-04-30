import pandas as pd
import numpy as np
import pandas_ta as ta

class HighBetaModel:
    """
    Model 6: High-Beta / ORB Engine - Version 2.1 (Performance Fix)
    Profile: Day Trading / Opening Range Breakout (First 15 Mins)
    """
    def __init__(self, min_itr=4.0, min_resilience=0.40, rr_target=1.0):
        self.min_itr = min_itr
        self.min_resilience = min_resilience
        self.rr_target = rr_target
        self.name = "M6_OPT"

    def evaluate(self, df):
        """
        Evaluates the historical 5-minute data to see if the stock 
        qualifies for an ORB trade TODAY.
        """
        if df is None or len(df) < 12: # Need at least an hour of 5m bars
            return False, {}

        # Group by day
        daily_groups = [group for _, group in df.groupby(df.index.date)]
        
        # BUG FIX: Allow evaluation of a single day if that's all that's provided
        # This allows the backtester to pass individual 'Yesterday' slices.
        if len(daily_groups) == 0:
            return False, {}
            
        # We evaluate the last available day in the provided dataframe
        yest_data = daily_groups[-1]
        
        # 1. Calculate Yesterday's Metrics
        y_open = yest_data['Open'].iloc[0]
        y_close = yest_data['Close'].iloc[-1]
        y_high = yest_data['High'].max()
        y_low = yest_data['Low'].min()
        
        y_range = y_high - y_low
        if y_range <= 0 or y_open <= 0: 
            return False, {"ITR": 0, "Resilience": 0}

        itr = (y_range / y_open) * 100
        resilience = (y_close - y_low) / y_range

        # 2. Apply Optimized Filters
        is_volatile = itr >= self.min_itr
        is_resilient = resilience >= self.min_resilience

        if is_volatile and is_resilient:
            return True, {
                "ITR": itr,
                "Resilience": resilience,
                "Strategy": "15-Min ORB",
                "Action": f"Buy if price breaks 09:15 High."
            }
            
        return False, {"ITR": itr, "Resilience": resilience}