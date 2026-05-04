import os
import json
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import pandas_ta as ta

# 1. IMPORT PRODUCTION ENGINES
from core.models.m1_trend import TrendModel as M1
from core.models.m2_revert import RevertModel as M2
from core.models.m3_breakout import BreakoutModel as M3
from core.models.m4_leadership import LeadershipModel as M4
from core.models.m6_high_beta import HighBetaModel as M6
from core.models.m9_controller import PortfolioController as M9

# ANSI Colors
CYAN, GREEN, YELLOW, RED, MAGENTA, GRAY, RESET = "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[95m", "\033[90m", "\033[0m"

DEBUG_MODE = True
DEBUG_WATCHLIST = ["BBRI", "TLKM", "GOTO", "AMMN", "ASII"] 
TARGET_DATE = "2026-04-27" 
REPORT_BUFFER = []

def log(text=""):
    print(text)
    clean_text = text.replace(CYAN, "").replace(GREEN, "").replace(YELLOW, "").replace(RED, "").replace(MAGENTA, "").replace(GRAY, "").replace(RESET, "")
    REPORT_BUFFER.append(clean_text)

def run_morning_report():
    report_date = TARGET_DATE if TARGET_DATE else datetime.now().strftime("%Y-%m-%d")
    
    log(f"\n" + "═"*85)
    log(f"{CYAN}🌅 WINTRA PORTFOLIO STRATEGY REPORT (M9 CONTROLLED) | {report_date}{RESET}")
    log("═"*85)

    # A. FETCH DATA & IHSG
    macro_tickers = {"IHSG": "^JKSE"}
    end_dt = pd.to_datetime(report_date) + timedelta(days=1)
    macro_data = yf.download(list(macro_tickers.values()), start="2026-01-01", end=end_dt, interval="1d", progress=False)
    ihsg_series = macro_data['Close']["^JKSE"].dropna()
    if ihsg_series.index.tz is not None: ihsg_series.index = ihsg_series.index.tz_localize(None)

    m1, m2, m3, m4, m6 = M1(), M2(), M3(), M4(), M6()
    m9 = M9(max_slots=4, max_per_model=2)
    
    current_regime = m1.detect_regime(ihsg_series)
    log(f"🌍 {CYAN}1. MARKET REGIME DETECTION:{RESET} {MAGENTA}{current_regime}{RESET}")

    # B. UNIVERSE SCAN
    data_path = os.path.join("core", "data", "idx80_list.json")
    with open(data_path, 'r') as f: universe = json.load(f).get('tickers', [])
    yf_tickers = [f"{t}.JK" for t in universe]
    market_data = yf.download(yf_tickers, period="6mo", end=end_dt, interval="1d", progress=False)
    if market_data.index.tz is not None: market_data.index = market_data.index.tz_localize(None)
    
    raw_signals = []

    log(f"\n📡 {CYAN}2. SCANNING UNIVERSE & PARAMETER AUDIT{RESET}")
    log("─"*85)
    
    for ticker in yf_tickers:
        symbol = ticker.replace('.JK', '')
        try:
            c, v, o, h, l = market_data['Close'][ticker].dropna(), market_data['Volume'][ticker].dropna(), market_data['Open'][ticker].dropna(), market_data['High'][ticker].dropna(), market_data['Low'][ticker].dropna()
            if len(c) < 60: continue

            # DEBUG AUDIT
            if DEBUG_MODE and symbol in DEBUG_WATCHLIST:
                log(f"\n{YELLOW}[DEBUG: {symbol}]{RESET}")
                avg_vol = v.iloc[-21:-1].mean()
                ema10_val = ta.ema(c, length=10).iloc[-1]
                ema20_val = ta.ema(c, length=20).iloc[-1]
                log(f"  M1 (Trend)  | EMA10: {ema10_val:.0f} vs EMA20: {ema20_val:.0f} | Vol Ratio: {v.iloc[-1]/avg_vol:.2f}x")
                log(f"  M4 (Alpha)  | Alpha Score: {m4.get_alpha_score(c, ihsg_series):+.2f}%")
                itr = ((h.iloc[-1] - l.iloc[-1]) / o.iloc[-1]) * 100
                res = (c.iloc[-1] - l.iloc[-1]) / (h.iloc[-1] - l.iloc[-1]) if (h.iloc[-1] - l.iloc[-1]) > 0 else 0
                log(f"  M6 (Beta)   | ITR: {itr:.1f}% | Resilience: {res:.2f}")

            # --- EXECUTION WITH KEYWORD ARGUMENTS (Prevent Positional Errors) ---
            if m4.evaluate(close_prices=c, volume_series=v, open_prices=o, high_prices=h, market_index_series=ihsg_series):
                raw_signals.append({'ticker': symbol, 'model': 'M4', 'raw_score': m4.get_alpha_score(c, ihsg_series), 'desc': 'Alpha Leader'})

            if m1.evaluate(close_prices=c, volume_series=v, market_index_series=ihsg_series):
                raw_signals.append({'ticker': symbol, 'model': 'M1', 'raw_score': 100 - (m1.get_proximity(c)*10), 'desc': 'Trend Ignition'})

            if m2.evaluate(close_prices=c, volume_series=v, open_prices=o, high_prices=h, low_prices=l, market_index_series=ihsg_series):
                raw_signals.append({'ticker': symbol, 'model': 'M2', 'raw_score': m2.get_elasticity_score(c), 'desc': 'Elastic Sniper'})

            if m3.evaluate(close_prices=c, volume_series=v, high_prices=h, low_prices=l, market_index_series=ihsg_series):
                raw_signals.append({'ticker': symbol, 'model': 'M3', 'raw_score': m3.get_breakout_strength(c, v)*10, 'desc': 'Stage 2 Breakout'})

            is_m6, m6_meta = m6.evaluate(pd.DataFrame({'Open':o, 'High':h, 'Low':l, 'Close':c}))
            if is_m6:
                raw_signals.append({'ticker': symbol, 'model': 'M6', 'raw_score': 50.0, 'desc': f'ITR: {m6_meta.get("ITR", 0):.1f}%'})
                
        except Exception as e:
            if symbol in DEBUG_WATCHLIST: log(f"  {RED}Error on {symbol}: {e}{RESET}")

    # D. TOURNAMENT
    log(f"\n🏆 {CYAN}3. THE WINTRA TOURNAMENT: M9 SELECTION{RESET}")
    log("─"*85)
    
    ranked = m9.rank_signals(raw_signals, current_regime)
    picks = m9.manage_exposure({}, ranked)

    if not picks:
        log(f"{YELLOW}⚠️ No high-conviction signals cleared the M9 filters today.{RESET}")
    else:
        for i, p in enumerate(picks):
            log(f" {i+1}. {p['ticker'].ljust(6)} | {p['model']:<8} | Score: {p['final_score']:>5.1f} | {p['desc']}")

    log(f"\n🌐 {CYAN}4. REGIME WEIGHTS (MODEL 9 CONTROL):{RESET}")
    log("─"*85)
    lookup = "BEAR" if current_regime == "DEFENSIVE" else current_regime
    w = m9.REGIME_PRIORITY.get(lookup, {})
    log(f"{GRAY}" + " | ".join([f"{k}: {v*100:.0f}%" for k, v in w.items() if v > 0]) + f"{RESET}")
    log("\n" + "═"*85 + "\n")

if __name__ == "__main__":
    run_morning_report()
