import os
import json
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime
from core.models.m1_trend import TrendModel

def run_morning_session():
    # 1. Setup & Intro
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"🌅 WINTRA MORNING REPORT | {now}")
    print("⚙️ System Profile: Aggressive / Adaptive Mode Active")
    print("─"*65)

    # 2. Load Universe
    data_path = os.path.join("core", "data", "idx80_list.json")
    if not os.path.exists(data_path):
        print("❌ Error: Universe data missing. Run core/scraper.py first.")
        return
        
    with open(data_path, 'r') as f:
        universe = json.load(f).get('tickers', [])
    
    yf_tickers = [f"{t}.JK" for t in universe]
    
    # 3. Fetch Market Context (IHSG + Tickers)
    print(f"📡 Scanning {len(yf_tickers)} tickers + IHSG Index...")
    all_symbols = yf_tickers + ["^JKSE"]
    market_data = yf.download(all_symbols, period="6mo", interval="1d", threads=False, progress=False)
    
    # 4. Detect Regime Personality
    m1 = TrendModel()
    ihsg_close = market_data['Close']["^JKSE"].dropna()
    regime = m1.detect_regime(ihsg_close)
    
    personality_map = {
        "BULL": "🎯 THE DISCIPLINED SNIPER (Neutral Winrate / Consistent Growth)",
        "SIDEWAYS": "🏹 THE ALPHA HUNTER (Best Winrate / Catching Outliers)",
        "BEAR": "🛡️ THE ELITE GUARD (Highest EV / Capital Protection Mode)"
    }
    
    print(f"🌍 Market Regime : {regime}")
    print(f"🧠 M1 Personality: {personality_map.get(regime)}")
    print("─"*65)

    # 5. Evaluate Ignitions
    passed_candidates = []
    close_data = market_data['Close']
    volume_data = market_data['Volume']

    for ticker in yf_tickers:
        try:
            symbol = ticker.replace('.JK', '')
            c_prices = close_data[ticker].dropna()
            v_series = volume_data[ticker].dropna()
            
            if m1.evaluate(c_prices, v_series, ihsg_close):
                prox = m1.get_proximity(c_prices)
                
                passed_candidates.append({
                    'ticker': symbol,
                    'price': c_prices.iloc[-1],
                    'proximity': prox
                })
        except:
            continue

    # 6. Output Final Ranking
    passed_candidates.sort(key=lambda x: x['proximity'])
    top_5 = passed_candidates[:5]

    if not top_5:
        print("⚠️ No High-Conviction Ignitions found. System suggests staying in CASH.")
    else:
        print(f"🏆 TOP {len(top_5)} IGNITION SIGNALS (Ranked by Proximity)")
        for i, item in enumerate(top_5):
            print(f"{i+1}. {item['ticker'].ljust(6)} | Price: Rp{item['price']:,.0f} | Proximity: +{item['proximity']:.2f}%")

    print("─"*65)
    print("🚀 Running Live Test... Good luck with the scan.")
    print("═"*65 + "\n")

if __name__ == "__main__":
    run_morning_session()
