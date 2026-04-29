import os
import json
import pandas as pd
import yfinance as yf
from datetime import datetime

# Import the production engines
from core.models.m1_trend import TrendModel as M1
from core.models.m2_revert_opt import RevertModel as M2
from core.models.m3_breakout import BreakoutModel as M3
from core.models.m4_leadership import LeadershipModel as M4

# ANSI Color Codes for Terminal UI
GRAY = "\033[90m"
RESET = "\033[0m"

# Global list to store the report for the Markdown export
REPORT_BUFFER = []

def log(text=""):
    """Prints to console AND saves to the Markdown buffer (stripping ANSI codes)."""
    print(text)
    clean_text = text.replace(GRAY, "").replace(RESET, "")
    REPORT_BUFFER.append(clean_text)

class WintraTournament:
    """The Morning Report Priority Engine."""
    REGIME_WEIGHTS = {
        "BULL": {
            "M4_Alpha": 0.50,
            "M1_Trend": 0.30,
            "M3_Breakout": 0.20,
            "M2_Revert": 0.00
        },
        "BEAR": {
            "M2_Revert": 0.40,
            "M1_Trend": 0.35,
            "M3_Breakout": 0.15,
            "M4_Alpha": 0.10
        },
        "SIDEWAYS": {
            "M4_Alpha": 0.35,
            "M1_Trend": 0.35,
            "M3_Breakout": 0.20,
            "M2_Revert": 0.10
        }
    }

    @staticmethod
    def normalize_score(model_name, raw_value):
        """Converts disparate metrics into a standardized 1-100 Conviction Score."""
        if model_name == "M1_Trend":
            score = max(0, 100 - (raw_value * 10))
            return score
        elif model_name == "M2_Revert":
            score = min(100, raw_value * 6.6)
            return score
        elif model_name == "M3_Breakout":
            score = min(100, raw_value * 20)
            return score
        elif model_name == "M4_Alpha":
            score = min(100, raw_value * 6.6)
            return score
        return 0.0

    @staticmethod
    def rank_candidates(candidates, regime):
        weights = WintraTournament.REGIME_WEIGHTS.get(regime, WintraTournament.REGIME_WEIGHTS["SIDEWAYS"])
        for c in candidates:
            model_weight = weights.get(c['model'], 0)
            normalized_score = WintraTournament.normalize_score(c['model'], c['metric_val'])
            c['tournament_score'] = normalized_score * model_weight
            c['weight_applied'] = model_weight
            
        return sorted(candidates, key=lambda x: x['tournament_score'], reverse=True)

def fetch_macro_context():
    """Fetches IHSG, USD/IDR, and Crude Oil data for the macro view."""
    macro_tickers = {
        "IHSG": "^JKSE",
        "USD/IDR": "IDR=X",
        "Crude Oil": "CL=F"
    }
    
    print("📡 Fetching Global Macro Indicators...")
    data = yf.download(list(macro_tickers.values()), period="5d", interval="1d", progress=False)
    
    macro_summary = {}
    for name, ticker in macro_tickers.items():
        try:
            close_prices = data['Close'][ticker].dropna()
            if len(close_prices) >= 2:
                curr = close_prices.iloc[-1]
                prev = close_prices.iloc[-2]
                pct_change = ((curr - prev) / prev) * 100
                macro_summary[name] = {"price": curr, "change": pct_change}
            else:
                macro_summary[name] = {"price": 0.0, "change": 0.0}
        except:
            macro_summary[name] = {"price": 0.0, "change": 0.0}
            
    ihsg_series = data['Close']["^JKSE"].dropna()
    if ihsg_series.index.tz is not None:
        ihsg_series.index = ihsg_series.index.tz_localize(None)
        
    return macro_summary, ihsg_series

def run_morning_report():
    now = datetime.now().strftime("%Y-%m-%d | %H:%M WIB")
    log(f"\n" + "═"*75)
    log(f"🌅 WINTRA INTEGRATED MORNING REPORT | {now}")
    log("═"*75)

    macro_data, ihsg_series = fetch_macro_context()
    m1, m2, m3, m4 = M1(), M2(), M3(), M4()
    current_regime = m1.detect_regime(ihsg_series)
    
    log("\n🌍 1. MACRO & MARKET CONTEXT")
    log("─"*75)
    log(f"Market Regime   : {current_regime}")
    
    for name, stats in macro_data.items():
        sign = "+" if stats['change'] > 0 else ""
        if name == "USD/IDR":
            log(f"{name:<15} : Rp {stats['price']:,.0f} ({sign}{stats['change']:.2f}%)")
        elif name == "Crude Oil":
            log(f"{name:<15} : ${stats['price']:.2f}/bbl ({sign}{stats['change']:.2f}%)")
        else:
            log(f"{name:<15} : {stats['price']:,.2f} ({sign}{stats['change']:.2f}%)")

    active_weights = WintraTournament.REGIME_WEIGHTS.get(current_regime, {})

    data_path = os.path.join("core", "data", "idx80_list.json")
    if not os.path.exists(data_path):
        log("\n❌ Error: Universe data missing. Run scraper first.")
        return
        
    with open(data_path, 'r') as f:
        universe = json.load(f).get('tickers', [])
    
    yf_tickers = [f"{t}.JK" for t in universe]
    print(f"\n📡 Scanning {len(yf_tickers)} IDX80 Tickers...") # Print only, no need in MD log
    market_data = yf.download(yf_tickers, period="6mo", interval="1d", progress=False)
    
    if market_data.index.tz is not None:
        market_data.index = market_data.index.tz_localize(None)
    
    candidates_passed = []
    candidates_failed = []

    # 3. Evaluate Engines
    for ticker in yf_tickers:
        try:
            symbol = ticker.replace('.JK', '')
            c = market_data['Close'][ticker].dropna()
            v = market_data['Volume'][ticker].dropna()
            o = market_data['Open'][ticker].dropna()
            h = market_data['High'][ticker].dropna()
            l = market_data['Low'][ticker].dropna()
            
            if len(c) < 60: continue

            # M1: Trend
            if active_weights.get("M1_Trend", 0) > 0:
                ema_f = c.ewm(span=10, adjust=False).mean().iloc[-1]
                prox = ((c.iloc[-1] - ema_f) / ema_f) * 100
                if prox > 0:
                    is_passed = m1.evaluate(c, v, ihsg_series)
                    item = {'ticker': symbol, 'model': 'M1_Trend', 'metric_val': prox, 'price': c.iloc[-1], 'metric_name': 'Proximity', 'status': 'PASSED' if is_passed else 'FAILED'}
                    if is_passed: candidates_passed.append(item)
                    else: candidates_failed.append(item)

            # M2: Revert
            if active_weights.get("M2_Revert", 0) > 0:
                elast = m2.get_elasticity_score(c)
                is_passed = m2.evaluate(c, v, o, h, l, ihsg_series)
                item = {'ticker': symbol, 'model': 'M2_Revert', 'metric_val': elast, 'price': c.iloc[-1], 'metric_name': 'Stretch', 'status': 'PASSED' if is_passed else 'FAILED'}
                if is_passed: candidates_passed.append(item)
                else: candidates_failed.append(item)

            # M3: Breakout
            if active_weights.get("M3_Breakout", 0) > 0:
                strength = m3.get_breakout_strength(c, v)
                is_passed = m3.evaluate(c, v, h, l, ihsg_series)
                item = {'ticker': symbol, 'model': 'M3_Breakout', 'metric_val': strength, 'price': c.iloc[-1], 'metric_name': 'Vol Surge', 'status': 'PASSED' if is_passed else 'FAILED'}
                if is_passed: candidates_passed.append(item)
                else: candidates_failed.append(item)

            # M4: Alpha
            if active_weights.get("M4_Alpha", 0) > 0:
                alpha = m4.get_alpha_score(c, ihsg_series)
                is_passed = m4.evaluate(c, v, o, h, ihsg_series)
                item = {'ticker': symbol, 'model': 'M4_Alpha', 'metric_val': alpha, 'price': c.iloc[-1], 'metric_name': 'Alpha Outperf', 'status': 'PASSED' if is_passed else 'FAILED'}
                if is_passed: candidates_passed.append(item)
                else: candidates_failed.append(item)

        except Exception:
            continue

    log("\n🔍 2. INDIVIDUAL ENGINE SIGNALS & NEAR MISSES")
    log("─"*75)
    model_keys = ["M4_Alpha", "M1_Trend", "M3_Breakout", "M2_Revert"]
    
    for mod in model_keys:
        weight = active_weights.get(mod, 0)
        weight_str = f"{weight*100:>2.0f}% Weight"
        
        if weight == 0:
            log(f"[{mod:<11} | {weight_str}] 🛡️ OFF (Disabled to prevent value traps)\n")
            continue
            
        mod_passed = [c for c in candidates_passed if c['model'] == mod]
        mod_failed = [c for c in candidates_failed if c['model'] == mod]
            
        if mod == "M1_Trend":
            mod_passed.sort(key=lambda x: x['metric_val']) 
            mod_failed.sort(key=lambda x: x['metric_val']) 
        else:
            mod_passed.sort(key=lambda x: x['metric_val'], reverse=True) 
            mod_failed.sort(key=lambda x: x['metric_val'], reverse=True) 
            
        if not mod_passed:
            log(f"[{mod:<11} | {weight_str}] ⚠️ No tickers met all criteria today.")
        else:
            log(f"[{mod:<11} | {weight_str}] ✅ Triggered on {len(mod_passed)} ticker(s):")
            for i, c in enumerate(mod_passed[:3]):
                metric = f"{c['metric_val']:.2f}"
                if c['metric_name'] in ['Proximity', 'Stretch', 'Alpha Outperf']: metric += "%"
                elif c['metric_name'] == 'Vol Surge': metric += "x"
                log(f"   {i+1}. {c['ticker'].ljust(6)} | {c['metric_name']}: {metric}")
                
        if mod_failed:
            log(f"{GRAY}   --- Near Misses (Failed Quality Filters / Not Recommended) ---")
            for i, c in enumerate(mod_failed[:3]):
                metric = f"{c['metric_val']:.2f}"
                if c['metric_name'] in ['Proximity', 'Stretch', 'Alpha Outperf']: metric += "%"
                elif c['metric_name'] == 'Vol Surge': metric += "x"
                log(f"   {i+1}. {c['ticker'].ljust(6)} | {c['metric_name']}: {metric}{RESET}")
        log("") 

    # 3. Tournament Ranking (ONLY uses passed candidates)
    ranked_passed = WintraTournament.rank_candidates(candidates_passed, current_regime)
    
    log("🏆 3. THE WINTRA TOURNAMENT: TOP 5 CONVICTION TRADES")
    log("─"*75)
    
    seen_tickers = set()
    final_top_5 = []
    
    for c in ranked_passed:
        if c['ticker'] not in seen_tickers:
            final_top_5.append(c)
            seen_tickers.add(c['ticker'])
        if len(final_top_5) == 5:
            break

    if not final_top_5:
        log("🛡️ NO TRADES DETECTED. The models have rejected all current market setups.")
    else:
        for i, c in enumerate(final_top_5):
            t = c['ticker'].ljust(6)
            mod = c['model'].replace('_', ' ')
            score = c['tournament_score']
            metric = f"{c['metric_val']:.2f}"
            if c['metric_name'] in ['Proximity', 'Stretch', 'Alpha Outperf']: metric += "%"
            elif c['metric_name'] == 'Vol Surge': metric += "x"
            
            log(f" {i+1}. {t} | {mod:<13} | Score: {score:>5.1f} | {c['metric_name']}: {metric}")

    # 4. Expanded League (Passed + Failed)
    all_candidates = candidates_passed + candidates_failed
    ranked_all = WintraTournament.rank_candidates(all_candidates, current_regime)

    log("\n🌐 4. THE EXPANDED LEAGUE: TOP 10 OVERALL (Including Near Misses)")
    log("─"*75)

    seen_all = set()
    final_top_10 = []

    for c in ranked_all:
        if c['ticker'] not in seen_all:
            final_top_10.append(c)
            seen_all.add(c['ticker'])
        if len(final_top_10) == 10:
            break

    if not final_top_10:
        log("🛡️ NO STOCKS SCORED IN THE LEAGUE.")
    else:
        for i, c in enumerate(final_top_10):
            t = c['ticker'].ljust(6)
            mod = c['model'].replace('_', ' ')
            score = c['tournament_score']
            metric = f"{c['metric_val']:.2f}"
            if c['metric_name'] in ['Proximity', 'Stretch', 'Alpha Outperf']: metric += "%"
            elif c['metric_name'] == 'Vol Surge': metric += "x"
            
            if c['status'] == 'PASSED':
                log(f" {i+1:>2}. {t} | {mod:<13} | Score: {score:>5.1f} | {c['metric_name']}: {metric} | ✅ High Conviction")
            else:
                log(f"{GRAY} {i+1:>2}. {t} | {mod:<13} | Score: {score:>5.1f} | {c['metric_name']}: {metric} | ⚠️ Near Miss{RESET}")

    log("═"*75 + "\n")

    # SAVE TO MARKDOWN REPORT
    report_text = "\n".join(REPORT_BUFFER)
    # Add a code block wrapper so it renders nicely in standard Markdown viewers
    md_content = f"```text\n{report_text}\n```"
    
    with open("wintra_scheduled_report.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    
    print(f"💾 Scheduled Report successfully exported to: wintra_scheduled_report.md")

if __name__ == "__main__":
    run_morning_report()
