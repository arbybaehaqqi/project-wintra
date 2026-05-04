import os
import json
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import pandas_ta as ta
import inspect

# IMPORT SWING MODELS (Strictly matching sys_sync registry)
from core.models.m1_trend import TrendModel as M1
from core.models.m3_breakout import BreakoutModel as M3
from core.models.m4_leadership import LeadershipModel as M4
from core.models.m9_controller import PortfolioController as M9

# ANSI Colors
CYAN, GREEN, YELLOW, RED, MAGENTA, GRAY, RESET = "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[95m", "\033[90m", "\033[0m"

# Hardcoded Historical EV for Display
MODEL_EV = {"M1_Trend": "+1.86%", "M3_Breakout": "+2.57%", "M4_Alpha": "+2.41%"}
SWING_STOP_LOSS = -3.5 # 3.5% wide stop for 1-5 day swings

class SwingSimulator:
    def __init__(self):
        self.m1 = M1()
        self.m3 = M3()
        self.m4 = M4()
        self.m9 = M9()

    def fetch_market_data(self):
        print(f"{GRAY}📡 Fetching 70-days of Daily Data for Swing Test...{RESET}")
        list_path = os.path.join("core", "data", "idx80_list.json")
        if os.path.exists(list_path):
            with open(list_path, 'r') as f: universe = json.load(f).get('tickers', [])
        else:
            universe = ["BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ASII", "GOTO", "AMMN", "BREN", "SIDO", "MEDC", "ADRO", "PTBA", "UNVR", "BBTN", "ELSA", "ESSA", "KOTA", "SSIA"]
            
        yf_tickers = [f"{t}.JK" for t in universe]
        
        daily_data = yf.download(yf_tickers + ["^JKSE"], period="70d", interval="1d", progress=False)
        
        if daily_data.index.tz is not None: 
            daily_data.index = daily_data.index.tz_localize(None)
            
        return universe, daily_data

    def evaluate_morning(self, date_dt, universe, daily_data):
        ihsg_hist = daily_data['Close']["^JKSE"].loc[daily_data.index <= date_dt]
        if len(ihsg_hist) < 50: return None, None, None
        
        regime = self.m1.detect_regime(ihsg_hist)
        report = []
        
        diagnostics = {
            "total_scanned": len(universe),
            "valid_data": 0,
            "raw_m1": 0,
            "raw_m3": 0,
            "raw_m4": 0,
            "m1_near_misses": [],
            "m3_near_misses": [],
            "m4_near_misses": [],
            "ghost_rejections": []
        }
        
        for ticker in universe:
            sym = f"{ticker}.JK"
            if sym not in daily_data['Close']: continue
            
            d_hist = pd.DataFrame({
                'Open': daily_data['Open'][sym], 'High': daily_data['High'][sym],
                'Low': daily_data['Low'][sym], 'Close': daily_data['Close'][sym], 'Volume': daily_data['Volume'][sym]
            }).loc[daily_data.index <= date_dt].dropna()
            
            if len(d_hist) < 50: continue
            diagnostics["valid_data"] += 1
            
            c, v, o, h, l = d_hist['Close'], d_hist['Volume'], d_hist['Open'], d_hist['High'], d_hist['Low']
            
            try:
                atr_series = ta.atr(h, l, c, length=14)
                atr = atr_series.iloc[-1] if atr_series is not None else (c.iloc[-1] * 0.02)
            except:
                atr = c.iloc[-1] * 0.02
                
            prev_price = c.iloc[-1]
            
            # --- M1 DIAGNOSTIC ---
            diag_passed_m1 = False
            try:
                ema_f = ta.ema(c, length=10)
                ema_s = ta.ema(c, length=20)
                if ema_f is not None and ema_s is not None:
                    curr_p, curr_ef, curr_es = c.iloc[-1], ema_f.iloc[-1], ema_s.iloc[-1]
                    vol_thresh = 1.25 if regime == "BULL" else 1.80
                    is_stacked = bool(curr_p > curr_ef and curr_ef > curr_es)
                    avg_vol = v.iloc[-21:-1].mean()
                    vol_ratio = float(v.iloc[-1] / avg_vol) if avg_vol > 0 else 0.0
                    is_vol = bool(vol_ratio > vol_thresh)
                    
                    blocker = "None"
                    if not is_stacked: blocker = "Trend Not Stacked"
                    elif not is_vol: blocker = "Low Volume"

                    if blocker == "None": diag_passed_m1 = True

                    diagnostics["m1_near_misses"].append({
                        "ticker": ticker, "stacked": is_stacked, "vol_ratio": vol_ratio, 
                        "prox": float(((curr_p - curr_ef) / curr_ef) * 100), "blocker": blocker
                    })
            except: pass

            # --- M3 DIAGNOSTIC ---
            diag_passed_m3 = False
            try:
                ema20 = ta.ema(c, length=20)
                sma50 = ta.sma(c, length=50)
                if ema20 is not None and sma50 is not None and len(h) > 41:
                    curr_p, curr_h, curr_l, curr_v = c.iloc[-1], h.iloc[-1], l.iloc[-1], v.iloc[-1]
                    curr_e20, curr_s50 = ema20.iloc[-1], sma50.iloc[-1]
                    
                    res_ceil = h.iloc[-41:-1].max()
                    is_breakout = curr_p > res_ceil
                    
                    avg_vol_m3 = v.iloc[-21:-1].mean()
                    vol_mult_m3 = 2.5
                    is_vol_m3 = curr_v > (avg_vol_m3 * vol_mult_m3)
                    
                    day_range = (curr_h - curr_l) if (curr_h - curr_l) > 0 else 0.001
                    is_pivot_m3 = (curr_p - curr_l) / day_range >= (1 - 0.20) # Top 20%
                    
                    is_uptrend_m3 = (curr_p > curr_e20) and (curr_e20 > curr_s50)
                    stretch_m3 = ((curr_p - curr_e20) / curr_e20) * 100
                    is_not_ext_m3 = stretch_m3 <= 12.0
                    
                    blocker_m3 = "None"
                    if not is_uptrend_m3: blocker_m3 = "Not in Uptrend"
                    elif not is_breakout: blocker_m3 = f"No Breakout (Ceil: {res_ceil:,.0f})"
                    elif not is_vol_m3: blocker_m3 = f"Low Vol (Req 2.5x)"
                    elif not is_not_ext_m3: blocker_m3 = "Overextended"
                    elif not is_pivot_m3: blocker_m3 = "Failed Pivot"

                    if blocker_m3 == "None": diag_passed_m3 = True

                    diagnostics["m3_near_misses"].append({
                        "ticker": ticker, "breakout": is_breakout, 
                        "vol_ratio": curr_v / avg_vol_m3 if avg_vol_m3 > 0 else 0, "blocker": blocker_m3
                    })
            except: pass

            # --- M4 DIAGNOSTIC ---
            diag_passed_m4 = False
            try:
                df_m4 = pd.DataFrame({'Close': c, 'Open': o, 'Volume': v, 'High': h, 'IHSG': ihsg_hist}).dropna()
                if len(df_m4) >= 50:
                    df_m4['RS'] = df_m4['Close'] / df_m4['IHSG']
                    rs_e10 = ta.ema(df_m4['RS'], length=10)
                    rs_s20 = ta.sma(df_m4['RS'], length=20)
                    p_e10 = ta.ema(df_m4['Close'], length=10)
                    p_s20 = ta.sma(df_m4['Close'], length=20)
                    
                    if rs_e10 is not None and p_e10 is not None:
                        curr_rs = df_m4['RS'].iloc[-1]
                        curr_rs_e10 = rs_e10.iloc[-1]
                        curr_rs_s20 = rs_s20.iloc[-1]
                        curr_p_m4 = df_m4['Close'].iloc[-1]
                        curr_o_m4 = df_m4['Open'].iloc[-1]
                        curr_v_m4 = df_m4['Volume'].iloc[-1]
                        curr_p_e10 = p_e10.iloc[-1]
                        curr_p_s20 = p_s20.iloc[-1]
                        
                        is_healthy = curr_p_m4 > curr_p_e10 and curr_p_e10 > curr_p_s20
                        is_rs_trend = curr_rs > curr_rs_e10 and curr_rs_e10 > curr_rs_s20
                        
                        avg_vol_m4 = df_m4['Volume'].iloc[-21:-1].mean()
                        is_vol_m4 = curr_v_m4 > (avg_vol_m4 * 1.5)
                        
                        high_20 = df_m4['High'].iloc[-21:-1].max()
                        dist_to_high = ((high_20 - curr_p_m4) / curr_p_m4) * 100
                        is_near_high = dist_to_high <= 5.0
                        
                        is_not_ext_m4 = ((curr_p_m4 - curr_p_e10) / curr_p_e10) * 100 <= 5.0
                        is_green_m4 = curr_p_m4 > curr_o_m4
                        
                        blocker_m4 = "None"
                        if not is_healthy: blocker_m4 = "Stock Not in Uptrend"
                        elif not is_rs_trend: blocker_m4 = "RS Line Not Trending"
                        elif not is_vol_m4: blocker_m4 = "Low Vol (Req 1.5x)"
                        elif not is_near_high: blocker_m4 = f"Too far from High ({dist_to_high:.1f}%)"
                        elif not is_not_ext_m4: blocker_m4 = "Overextended"
                        elif not is_green_m4: blocker_m4 = "Red Candle"
                        
                        if blocker_m4 == "None": diag_passed_m4 = True
                        
                        diagnostics["m4_near_misses"].append({
                            "ticker": ticker, "healthy": is_healthy, "rs_trend": is_rs_trend,
                            "rs_mom": True, "blocker": blocker_m4
                        })
            except: pass


            # --- M1 ENGINE EVALUATION ---
            engine_m1_result = False
            raw_result = None
            try:
                raw_result = self.m1.evaluate(close_prices=c.copy(), volume_series=v.copy(), open_prices=o.copy(), high_prices=h.copy(), low_prices=l.copy(), market_index_series=ihsg_hist.copy())
                engine_m1_result = bool(raw_result)
            except Exception as e:
                diagnostics["ghost_rejections"].append(f"{ticker}: Engine crashed -> {e}")

            if diag_passed_m1 and not engine_m1_result:
                eng_ema_f = ta.ema(c.copy(), length=10)
                eng_ema_s = ta.ema(c.copy(), length=20)
                eng_regime = self.m1.detect_regime(ihsg_hist.copy())
                eng_vol_thresh = 1.25 if eng_regime == "BULL" else 1.80
                
                eng_p, eng_ef, eng_es = c.iloc[-1], eng_ema_f.iloc[-1], eng_ema_s.iloc[-1]
                eng_stacked = bool(eng_p > eng_ef and eng_ef > eng_es)
                eng_avg_v = v.iloc[-21:-1].mean()
                eng_is_vol = bool(v.iloc[-1] > (eng_avg_v * eng_vol_thresh))
                
                try:
                    engine_src = inspect.getsource(self.m1.evaluate)
                    src_formatted = "\n".join([f"      {line}" for line in engine_src.split('\n') if line.strip()])
                except Exception as e:
                    src_formatted = f"      [Source extraction failed: {e}]"
                
                trace_log = (
                    f"  > {ticker} Deep Trace (M1 Trend):\n"
                    f"    - Regime Check : Diag={regime} | Engine={eng_regime}\n"
                    f"    - Trend Stack  : Diag={is_stacked} | Engine={eng_stacked} (P:{eng_p:.2f} > EF:{eng_ef:.2f} > ES:{eng_es:.2f})\n"
                    f"    - Volume Check : Diag={is_vol} | Engine={eng_is_vol} (Current {v.iloc[-1]:.0f} > Req {eng_avg_v * eng_vol_thresh:.0f})\n"
                    f"    {RED}🚨 FATAL MISMATCH: Engine returned False despite passing all mathematical checks.{RESET}\n"
                    f"    {YELLOW}This confirms your local 'm1_trend.py' file contains different logic. Extracting your source code:{RESET}\n"
                    f"{GRAY}{src_formatted}{RESET}"
                )
                diagnostics["ghost_rejections"].append(trace_log)

            if engine_m1_result:
                diagnostics["raw_m1"] += 1
                try: prox = self.m1.get_proximity(c)
                except: prox = 5.0
                score = max(0, 100 - (prox * 5))
                report.append({'ticker': ticker, 'model': 'M1_Trend', 'raw_score': score, 'prev': prev_price, 'target': prev_price + (atr*2), 'ev': MODEL_EV['M1_Trend']})

            # --- M3 BREAKOUT EVALUATION ---
            engine_m3_result = False
            try:
                raw_m3 = self.m3.evaluate(close_prices=c.copy(), volume_series=v.copy(), high_prices=h.copy(), low_prices=l.copy(), market_index_series=ihsg_hist.copy())
                engine_m3_result = bool(raw_m3)
            except Exception as e:
                diagnostics["ghost_rejections"].append(f"{ticker}: M3 Engine crashed -> {e}")

            if diag_passed_m3 and not engine_m3_result:
                eng_e20 = ta.ema(c.copy(), length=20).iloc[-1]
                eng_s50 = ta.sma(c.copy(), length=50).iloc[-1]
                eng_p, eng_h, eng_l, eng_v = c.iloc[-1], h.iloc[-1], l.iloc[-1], v.iloc[-1]
                eng_res = h.iloc[-41:-1].max()
                eng_avg_v = v.iloc[-21:-1].mean()
                eng_day_rng = (eng_h - eng_l) if (eng_h - eng_l) > 0 else 0.001
                
                try:
                    engine_src = inspect.getsource(self.m3.evaluate)
                    src_formatted = "\n".join([f"      {line}" for line in engine_src.split('\n') if line.strip()])
                except Exception as e:
                    src_formatted = f"      [Source extraction failed: {e}]"
                
                trace_log = (
                    f"  > {ticker} Deep Trace (M3 Breakout):\n"
                    f"    - Breakout : P:{eng_p:.0f} > Ceil:{eng_res:.0f}\n"
                    f"    - Vol Surge: {eng_v:,.0f} > {eng_avg_v * 2.5:,.0f}\n"
                    f"    - Trend    : P:{eng_p:.0f} > E20:{eng_e20:.0f} > S50:{eng_s50:.0f}\n"
                    f"    - Stretch  : {((eng_p - eng_e20)/eng_e20)*100:.1f}% <= 12.0%\n"
                    f"    - Pivot    : {((eng_p - eng_l)/eng_day_rng)*100:.1f}% >= 80%\n"
                    f"    {RED}🚨 FATAL MISMATCH: M3 Engine returned False despite passing math checks.{RESET}\n"
                    f"    {YELLOW}Extracting your source code:{RESET}\n"
                    f"{GRAY}{src_formatted}{RESET}"
                )
                diagnostics["ghost_rejections"].append(trace_log)

            if engine_m3_result:
                diagnostics["raw_m3"] += 1
                try: str_score = self.m3.get_breakout_strength(c, v)
                except: str_score = 1.0
                report.append({'ticker': ticker, 'model': 'M3_Breakout', 'raw_score': str_score * 25, 'prev': prev_price, 'target': prev_price + (atr*3), 'ev': MODEL_EV['M3_Breakout']})

            # --- M4 LEADERSHIP EVALUATION ---
            engine_m4_result = False
            try:
                raw_m4 = self.m4.evaluate(close_prices=c.copy(), volume_series=v.copy(), open_prices=o.copy(), high_prices=h.copy(), market_index_series=ihsg_hist.copy())
                engine_m4_result = bool(raw_m4)
            except Exception as e:
                diagnostics["ghost_rejections"].append(f"{ticker}: M4 Engine crashed -> {e}")

            if diag_passed_m4 and not engine_m4_result:
                df_m4 = pd.DataFrame({'Close': c.copy(), 'Open': o.copy(), 'Volume': v.copy(), 'High': h.copy(), 'IHSG': ihsg_hist.copy()}).dropna()
                df_m4['RS'] = df_m4['Close'] / df_m4['IHSG']
                rs_e10 = ta.ema(df_m4['RS'], length=10).iloc[-1]
                rs_s20 = ta.sma(df_m4['RS'], length=20).iloc[-1]
                p_e10 = ta.ema(df_m4['Close'], length=10).iloc[-1]
                p_s20 = ta.sma(df_m4['Close'], length=20).iloc[-1]
                curr_rs = df_m4['RS'].iloc[-1]
                eng_p = df_m4['Close'].iloc[-1]
                eng_v = df_m4['Volume'].iloc[-1]
                avg_v = df_m4['Volume'].iloc[-21:-1].mean()

                try:
                    engine_src = inspect.getsource(self.m4.evaluate)
                    src_formatted = "\n".join([f"      {line}" for line in engine_src.split('\n') if line.strip()])
                except Exception as e:
                    src_formatted = f"      [Source extraction failed: {e}]"
                
                trace_log = (
                    f"  > {ticker} Deep Trace (M4 Alpha):\n"
                    f"    - Uptrend  : P:{eng_p:.0f} > E10:{p_e10:.0f} > S20:{p_s20:.0f}\n"
                    f"    - RS Trend : Curr RS:{curr_rs:.4f} > RS E10:{rs_e10:.4f} > RS S20:{rs_s20:.4f}\n"
                    f"    - Vol Surge: {eng_v:,.0f} > {avg_v * 1.5:,.0f}\n"
                    f"    {RED}🚨 FATAL MISMATCH: M4 Engine returned False despite passing math checks.{RESET}\n"
                    f"    {YELLOW}Extracting your source code:{RESET}\n"
                    f"{GRAY}{src_formatted}{RESET}"
                )
                diagnostics["ghost_rejections"].append(trace_log)

            if engine_m4_result:
                diagnostics["raw_m4"] += 1
                alpha_score = 1.0
                if hasattr(self.m4, 'get_alpha_score'):
                    try: alpha_score = self.m4.get_alpha_score(c, ihsg_hist)
                    except: pass
                report.append({'ticker': ticker, 'model': 'M4_Alpha', 'raw_score': max(0, alpha_score * 10), 'prev': prev_price, 'target': prev_price + (atr*2.5), 'ev': MODEL_EV['M4_Alpha']})

        ranked_report = self.m9.rank_signals(report, regime) if report else []
        return ranked_report, regime, diagnostics

    def simulate_forward_performance(self, ticker, entry_date, daily_data):
        sym = f"{ticker}.JK"
        future_data = daily_data.loc[daily_data.index > entry_date]
        if sym not in future_data.columns.levels[1] if isinstance(future_data.columns, pd.MultiIndex) else sym not in future_data:
            return None
            
        future_df = pd.DataFrame({
            'High': daily_data['High'][sym], 'Low': daily_data['Low'][sym], 'Close': daily_data['Close'][sym]
        }).loc[daily_data.index > entry_date].dropna().head(5)
        
        if future_df.empty: return None
        
        entry_price = daily_data['Close'][sym].loc[daily_data.index <= entry_date].dropna().iloc[-1]
        
        max_high = future_df['High'].max()
        min_low = future_df['Low'].min()
        final_close = future_df['Close'].iloc[-1]
        
        max_gain = ((max_high - entry_price) / entry_price) * 100
        max_drawdown = ((min_low - entry_price) / entry_price) * 100
        
        if max_drawdown <= SWING_STOP_LOSS:
            final_return = SWING_STOP_LOSS
            status = f"{RED}STOPPED OUT{RESET}"
        else:
            final_return = ((final_close - entry_price) / entry_price) * 100
            status = f"{GREEN}HELD{RESET}" if final_return > 0 else f"{YELLOW}HELD{RESET}"
            
        return {
            "max_gain": max_gain, "max_drawdown": max_drawdown, "final_return": final_return,
            "status": status, "days_tracked": len(future_df)
        }

if __name__ == "__main__":
    sim = SwingSimulator()
    universe, daily_data = sim.fetch_market_data()
    unique_dates = daily_data.dropna(subset=[('Close', '^JKSE')]).index.unique().sort_values()
    
    if len(unique_dates) >= 6:
        target_date = unique_dates[-6]
        date_str = target_date.strftime("%Y-%m-%d")
        
        report, regime, diag = sim.evaluate_morning(target_date, universe, daily_data)
        
        print(f"\n" + "═"*85)
        print(f"🌅 WINTRA SWING BUCKET REPORT | {date_str} | REGIME: {regime}")
        print("═"*85)
        
        print(f"\n🔍 {YELLOW}DIAGNOSTICS & SYSTEM AUDIT{RESET}")
        print("─"*85)
        print(f"Data Integrity : {diag['valid_data']}/{diag['total_scanned']} tickers had sufficient historical data.")
        print(f"Raw Setup Hits : M1 Trend ({diag['raw_m1']}) | M3 Breakout ({diag['raw_m3']}) | M4 Alpha ({diag['raw_m4']})")
        
        if diag['ghost_rejections']:
            print(f"\n🚨 {RED}GHOST REJECTIONS DETECTED (Deep Trace Active){RESET}")
            for ghost in diag['ghost_rejections']:
                print(f"{ghost}")
        
        lookup_regime = "BEAR" if regime == "DEFENSIVE" else regime
        weights = sim.m9.REGIME_PRIORITY.get(lookup_regime, {})
        vetoed = [m for m in ["M1", "M3", "M4"] if weights.get(m, 0) == 0]
        if vetoed:
            print(f"M9 Controller  : {RED}VETO ACTIVE{RESET} -> {', '.join(vetoed)} models are disabled in a {lookup_regime} market.")
            
        # M1 DIAGNOSTICS PRINT
        print(f"\nTop 3 Closest M1 Candidates (Trend Engine):")
        sorted_m1 = sorted(diag["m1_near_misses"], key=lambda x: (x['stacked'], x['vol_ratio']), reverse=True)
        vol_req = 1.25 if regime == "BULL" else 1.80
        for i, m in enumerate(sorted_m1[:3]):
            stack_str = f"{GREEN}Yes{RESET}" if m['stacked'] else f"{RED}No{RESET}"
            vol_str = f"{GREEN if m['vol_ratio'] >= vol_req else YELLOW}{m['vol_ratio']:.1f}x{RESET}"
            blocker_str = f"{RED}{m['blocker']}{RESET}" if m['blocker'] != "None" else f"{GREEN}PASSED{RESET}"
            print(f"  {i+1}. {m['ticker'].ljust(5)} | Trend: {stack_str:<13} | Vol: {vol_str:<13} | Prox: {m['prox']:>+5.1f}% | Blocker: {blocker_str}")
            
        # M3 DIAGNOSTICS PRINT
        print(f"\nTop 3 Closest M3 Candidates (Breakout Engine):")
        sorted_m3 = sorted(diag["m3_near_misses"], key=lambda x: (x['breakout'], x['vol_ratio']), reverse=True)
        for i, m in enumerate(sorted_m3[:3]):
            bo_str = f"{GREEN}Yes{RESET}" if m['breakout'] else f"{RED}No{RESET}"
            vol_str = f"{GREEN if m['vol_ratio'] >= 2.5 else YELLOW}{m['vol_ratio']:.1f}x{RESET}"
            blocker_str = f"{RED}{m['blocker']}{RESET}" if m['blocker'] != "None" else f"{GREEN}PASSED{RESET}"
            print(f"  {i+1}. {m['ticker'].ljust(5)} | Breakout: {bo_str:<10} | Vol: {vol_str:<10} | Blocker: {blocker_str}")

        # M4 DIAGNOSTICS PRINT
        print(f"\nTop 3 Closest M4 Candidates (Alpha Engine):")
        sorted_m4 = sorted(diag["m4_near_misses"], key=lambda x: (x['healthy'], x['rs_trend'], x['rs_mom']), reverse=True)
        for i, m in enumerate(sorted_m4[:3]):
            h_str = f"{GREEN}Yes{RESET}" if m['healthy'] else f"{RED}No{RESET}"
            rs_str = f"{GREEN}Yes{RESET}" if m['rs_trend'] else f"{RED}No{RESET}"
            mom_str = f"{GREEN}Yes{RESET}" if m['rs_mom'] else f"{RED}No{RESET}"
            blocker_str = f"{RED}{m['blocker']}{RESET}" if m['blocker'] != "None" else f"{GREEN}PASSED{RESET}"
            print(f"  {i+1}. {m['ticker'].ljust(5)} | Uptrend: {h_str:<10} | RS Trend: {rs_str:<9} | RS Mom: {mom_str:<9} | Blocker: {blocker_str}")

        print("─"*85)
        
        if not report:
            print(f"\n{GRAY}  No SWING signals generated for this date.{RESET}")
        else:
            print(f"\n🏆 {CYAN}Swing Tournament (Top 5 Candidates){RESET}")
            print("─"*85)
            for i, p in enumerate(report[:5]):
                print(f"{i+1}. {p['ticker'].ljust(5)} ({p['final_score']:>5.1f} pts) | Prev: Rp{p['prev']:<6,.0f} | Target: Rp{p['target']:<6,.0f} | EV: {GREEN}{p['ev']}{RESET} | {p['model']}")
            
            print(f"\n📈 {MAGENTA}5-DAY FORWARD PERFORMANCE GAUNTLET (T+1 to T+5){RESET}")
            print(f"{GRAY}Stop Loss Hardcoded at {SWING_STOP_LOSS}%{RESET}")
            print("─"*85)
            print(f"{'Ticker':<6} | {'Max Peak':<10} | {'Max Drawdown':<15} | {'Final Return':<13} | {'Status'}")
            print("─"*85)
            
            for p in report[:5]:
                perf = sim.simulate_forward_performance(p['ticker'], target_date, daily_data)
                if perf:
                    peak_str = f"{GREEN}{perf['max_gain']:>+6.2f}%{RESET}" if perf['max_gain'] > 0 else f"{GRAY}{perf['max_gain']:>+6.2f}%{RESET}"
                    dd_str = f"{RED}{perf['max_drawdown']:>+6.2f}%{RESET}" if perf['max_drawdown'] < 0 else f"{GRAY}{perf['max_drawdown']:>+6.2f}%{RESET}"
                    ret_str = f"{GREEN if perf['final_return'] > 0 else RED}{perf['final_return']:>+6.2f}%{RESET}"
                    print(f"{p['ticker']:<6} | {peak_str:<19} | {dd_str:<24} | {ret_str:<22} | {perf['status']} ({perf['days_tracked']}d)")
                    
        print("═"*85 + "\n")
    else:
        print(f"{RED}❌ Insufficient historical data to run a 5-day backward anchor.{RESET}")
