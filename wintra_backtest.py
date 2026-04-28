import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from wintra_engine import WintraEngine

def run_wintra_tournament(start_date="2025-10-01", end_date="2026-04-27"):
    engine = WintraEngine()
    tickers = engine.universe
    macro_map = engine.macro_tickers
    
    print(f"🚀 Project Wintra: Starting 4-MODEL Tournament")
    print(f"📅 Period: {start_date} to {end_date}")
    
    # 1. Load All Historical Data
    all_symbols = tickers + list(macro_map.values())
    data = yf.download(all_symbols, start=start_date, end=end_date, interval="1d", progress=False)

    # --- FIX FOR KEYERROR: ADJ CLOSE ---
    # Check if 'Adj Close' exists in columns, otherwise use 'Close'
    price_col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
    print(f"✅ Using {price_col} for calculations.")
    
    close_prices = data[price_col][tickers]
    results_records = []

    # 2. The Simulation Loop
    for i in range(50, len(data)):
        current_date = data.index[i]
        history = data.iloc[:i] 
        
        macro_signals = {}
        try:
            # Applying the fix to the macro indicators too
            oil_history = data[price_col][macro_map['Oil']]
            gold_history = data[price_col][macro_map['Gold']]
            idr_history = data[price_col][macro_map['USDIDR']]
            
            oil_change = oil_history.iloc[i-1] / oil_history.iloc[i-2] - 1
            gold_change = gold_history.iloc[i-1] / gold_history.iloc[i-2] - 1
            idr_change = idr_history.iloc[i-1] / idr_history.iloc[i-2] - 1
            
            macro_signals['MEDC.JK'] = oil_change > 0.015
            macro_signals['AMMN.JK'] = gold_change > 0.015
            macro_signals['ADRO.JK'] = idr_change > 0.005
        except Exception as e:
            pass

        daily_returns = {"M1": [], "M2": [], "M3": [], "M4": [], "Ensemble": []}
        
        # We use standard 'Close' and 'Open' for the intraday return calculation
        today_open = data['Open'].iloc[i]
        today_close = data['Close'].iloc[i]
        t0_return = (today_close / today_open) - 1 - 0.003 # 0.3% Fee included

        for ticker in tickers:
            try:
                # Isolate ticker history using the smart price_col
                t_history = history.xs(ticker, axis=1, level=1).dropna()
                # Ensure we pass the right column name to your indicator calculator
                latest = engine.calculate_indicators(t_history)
                
                m1 = (latest['MA5'] > latest['MA20']) and (latest['Close'] > latest['MA50']) and (50 < latest['RSI'] < 70)
                m2 = (latest['RSI'] < 30) and (latest['Close'] <= latest['BB_Lower'] * 1.01)
                m3 = latest['Volume'] > (latest['Vol_20'] * 2.0)
                m4 = macro_signals.get(ticker, False)
                
                ret = t0_return[ticker]
                if m1: daily_returns["M1"].append(ret)
                if m2: daily_returns["M2"].append(ret)
                if m3: daily_returns["M3"].append(ret)
                if m4: daily_returns["M4"].append(ret)
                if m1 or m2 or m3 or m4: daily_returns["Ensemble"].append(ret)
            except: continue

        day_results = {k: np.mean(v) if v else 0 for k, v in daily_returns.items()}
        day_results['Date'] = current_date
        results_records.append(day_results)

    # 4. Final Comparison & Visualization
    report = pd.DataFrame(results_records).set_index('Date')
    cum_ret = (1 + report).cumprod() - 1

    print("\n" + "="*40)
    print(f"{'MODEL':<20} | {'TOTAL RETURN':>15}")
    print("="*40)
    for col in cum_ret.columns:
        print(f"{col:<20} | {cum_ret[col].iloc[-1]*100:>13.2f}%")
    
    # Plotting
    cum_ret.plot(figsize=(12,6), grid=True)
    plt.title("Project Wintra: 4-Model Tournament (Including Fees)")
    plt.ylabel("Cumulative Return (%)")
    plt.show()

if __name__ == "__main__":
    run_wintra_tournament()
