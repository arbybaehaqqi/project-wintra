import yfinance as yf
import pandas as pd
import numpy as np

def run_ranked_discovery(target_stock="MDKA.JK"):
    macro_indicators = {
        'Coal_Proxy': 'BTU',        # Peabody Energy (Reliable Coal proxy)
        'Agri_Proxy': 'DBA',        # Invesco Agriculture (Best CPO/Agri proxy)
        'Soy_Oil': 'ZL=F',          # Soybean Oil (The only reliable CPO future)
        'Mining_ETF': 'PICK',       # Global Mining Producers
        'Copper': 'HG=F', 'Gold': 'GC=F', 'Silver': 'SI=F',
        'Brent_Oil': 'BZ=F', 'WTI_Oil': 'CL=F',
        'Mining_Sector': 'PICK', 'Metals_Mining': 'XME',
        'USDIDR': 'IDR=X', 'DXY_Index': 'DX-Y.NYB',
        'US_10Y_Yield': '^TNX', 'Fear_Index': '^VIX',
        'IHSG_Bench': '^JKSE', 'Indo_Proxy': 'EIDO',
        'Hang_Seng': '^HSI', 'Shanghai': '000001.SS', 'SP500': '^GSPC'
    }
    
    all_tickers = [target_stock] + list(macro_indicators.values())
    print(f"📡 Windra is generating a Strategic Leaderboard for {target_stock}...")

    # Fetch Data
    data = yf.download(all_tickers, period="1y", interval="1d", progress=False)
    price_col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
    returns = data[price_col].ffill().pct_change(fill_method=None).dropna()
    
    # Calculate Correlation
    corr_matrix = returns.corr()
    target_corr = corr_matrix[target_stock].drop(target_stock, errors='ignore')
    
    # Create DataFrame
    inv_map = {v: k for k, v in macro_indicators.items()}
    results = []
    for ticker, score in target_corr.items():
        results.append({'Parameter': inv_map.get(ticker, ticker), 'r': score})
    
    df = pd.DataFrame(results)

    # --- THE SORTING LOGIC ---
    # Sort by raw correlation (Highest Positive to Lowest Negative)
    df = df.sort_values(by='r', ascending=False)

    print("\n🏆 PROJECT WINTRA: STRATEGIC LEADERBOARD")
    print("─────────────────────────────────────────────────────────────")
    print(f"{'PARAMETER':<15} | {'CORR (r)':>8} | {'ROLE IN PORTFOLIO'}")
    print("─────────────────────────────────────────────────────────────")
    
    for _, row in df.iterrows():
        r = row['r']
        # Define the Role
        if r > 0.4: role = "🚀 Primary Driver (Strong)"
        elif r > 0.15: role = "📈 Positive Ally"
        elif r < -0.4: role = "🛑 Strong Drag (Enemy)"
        elif r < -0.15: role = "📉 Negative Pressure"
        else: role = "⚖️ Neutral / Noise"
        
        print(f"{row['Parameter']:<15} | {r:>8.3f} | {role}")
    
    print("─────────────────────────────────────────────────────────────")
    print("Sorted from 'Best Friend' to 'Worst Enemy'.")

if __name__ == "__main__":
    # You can change this to "BBCA.JK" or "BBRI.JK" to see the Bank Personality!
    run_ranked_discovery("MDKA.JK")
