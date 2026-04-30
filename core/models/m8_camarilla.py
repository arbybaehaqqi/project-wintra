import pandas as pd

class RangeScalperModel:
    """
    Model 8: Range Scalper (Camarilla Ping-Pong)
    Profile: Day Trading / Range-Bound Scalping
    Logic: Buys the S3 Support Floor, Targets the Mean (Yesterday's Close).

    Expected Setup:
    - Min ITR: > 2.0% (Stock must be volatile enough to scalp)
    - Max Resilience: < 0.60 (Stock must NOT be in a runaway breakout)
    - Target: Mean Reversion to Yesterday's Close
    - Stop: S4 (Breakdown of the daily range)
    """
    def __init__(self, min_itr=2.0, max_resilience=0.60):
        self.min_itr = min_itr
        self.max_resilience = max_resilience
        self.name = "M8_CAMARILLA"

    def evaluate(self, ticker, df):
        """
        Evaluates the historical 5-minute data to calculate Camarilla zones TODAY.
        """
        if df is None or len(df) < 66: 
            return False, {}

        # Group by day to isolate yesterday's data
        daily_groups = [group for _, group in df.groupby(df.index.date)]
        if len(daily_groups) < 2: 
            return False, {}
            
        yest_data = daily_groups[-1]
        
        if len(yest_data) < 12: 
            return False, {}

        # 1. Day 1 Metrics
        y_o = yest_data['Open'].iloc[0]
        y_h = yest_data['High'].max()
        y_l = yest_data['Low'].min()
        y_c = yest_data['Close'].iloc[-1]
        
        y_range = y_h - y_l
        if y_range <= 0 or y_o <= 0: 
            return False, {}

        itr = (y_range / y_o) * 100
        resilience = (y_c - y_l) / y_range

        # 2. Camarilla Math
        s3 = y_c - (y_range * 1.1 / 4)
        s4 = y_c - (y_range * 1.1 / 2)
        r3 = y_c + (y_range * 1.1 / 4)

        # 3. Setup Filter
        # Must be volatile, but closed in the middle (choppy behavior)
        if itr >= self.min_itr and resilience <= self.max_resilience:
            return True, {
                "Strategy": "Camarilla Ping-Pong",
                "Action": f"Buy the S3 Floor at Rp {s3:,.0f}",
                "Buy_Zone": s3,
                "Target": y_c,
                "Cut_Loss": s4,
                "ITR": itr,
                "Resilience": resilience
            }
            
        return False, {}