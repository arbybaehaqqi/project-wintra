import os
import pandas as pd
import numpy as np
import json
import io
from datetime import datetime
import pandas_ta as ta

# 1. STRICT SYNCED IMPORTS (Matched exactly to sys_sync.py)
from core.models.m1_trend import TrendModel as M1
from core.models.m2_revert import RevertModel as M2
from core.models.m3_breakout import BreakoutModel as M3
from core.models.m4_leadership import LeadershipModel as M4
from core.models.m5_defensive import DefensiveModel as M5
from core.models.m6_high_beta import HighBetaModel as M6
from core.models.m7_washout import WashoutModel as M7
from core.models.m8_camarilla import RangeScalperModel as M8
from core.models.m9_controller import PortfolioController as M9

# --- GAUNTLET V25: THE RISK PARITY ENGINE ---
STARTING_BALANCE = 100_000_000 
LOT_SIZE = 100
FEE_BUY = 0.0015                
FEE_SELL = 0.0025               
LIMIT_ENTRY_DISCOUNT = 0.0020   
MARKET_SLIPPAGE_BETA = 0.0015   
LIQUIDITY_MAX_PARTICIPATION = 0.05  

# Risk Calibration
M9_BASE_THRESHOLD = 12.0        
BULL_HEAT = 0.010               # 1.0% Risk per trade
BEAR_HEAT = 0.003               # 0.3% Risk per trade
DRAWDOWN_HALFLIFE = 0.08        
MAX_DRAWDOWN_RECOVERY_MODE = 0.15 

# Adaptive Parameters per Regime
REGIME_CONFIG = {
    "BULL": {
        "stop_atr": 2.5, "ext_threshold": 12.0, "time_exit": 4, 
        "be_trigger": 0.6, "bolt_trigger": 1.0, "lock_profit": False
    },
    "SIDEWAYS": {
        "stop_atr": 1.7, "ext_threshold": 8.0, "time_exit": 2, 
        "be_trigger": 0.5, "bolt_trigger": 0.8, "lock_profit": 1.5
    },
    "BEAR": {
        "stop_atr": 1.5, "ext_threshold": 6.0, "time_exit": 1, 
        "be_trigger": 0.4, "bolt_trigger": 0.6, "lock_profit": 1.0
    }
}

INTRADAY_CACHE_DIR = "core/data/intraday_cache"
DAILY_CACHE_FILE = "core/data/m2_training_cache.json"

# ANSI Colors
CYAN, GREEN, YELLOW, RED, MAGENTA, GRAY, RESET = "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[95m", "\033[90m", "\033[0m"

def load_daily_data():
    if not os.path.exists(DAILY_CACHE_FILE): return None, None
    with open(DAILY_CACHE_FILE, 'r') as f: cache = json.load(f)
    ihsg = pd.read_json(io.StringIO(cache['ihsg']))
    ihsg.index = pd.to_datetime(ihsg.index)
    universe = {t: pd.read_json(io.StringIO(df)) for t, df in cache['tickers'].items()}
    for t in universe: universe[t].index = pd.to_datetime(universe[t].index)
    return universe, ihsg

def load_intraday_data():
    if not os.path.exists(INTRADAY_CACHE_DIR): return {}
    universe = {}
    for f in os.listdir(INTRADAY_CACHE_DIR):
        if not f.endswith(".csv"): continue
        t = f.split("_")[0]
        df = pd.read_csv(os.path.join(INTRADAY_CACHE_DIR, f))
        time_col = next((c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()), None)
        if time_col:
            df[time_col] = pd.to_datetime(df[time_col])
            df.set_index(time_col, inplace=True)
        else:
            df.index = pd.to_datetime(df.index)
        if not df.empty and df.index.hour[0] < 7:
            df.index = df.index + pd.Timedelta(hours=7)
        universe[t] = df
    return universe

class HardenedPortfolioManager:
    def __init__(self, max_slots):
        self.max_slots = max_slots
        self.balance = STARTING_BALANCE
        self.holdings = {} 
        self.history = []
        self.model_stats = {}
        self.peak_equity = STARTING_BALANCE

    def calculate_adv_atr(self, daily_df, date_dt):
        try:
            hist = daily_df.loc[daily_df.index < date_dt]
            if len(hist) < 14: return 0, 0
            atr_series = ta.atr(hist['High'], hist['Low'], hist['Close'], length=14)
            atr_val = atr_series.iloc[-1] if (atr_series is not None and not atr_series.empty) else 0
            adv = (hist['Close'] * hist['Volume']).iloc[-14:].mean()
            return adv, atr_val
        except: return 0, 0

    def update_trailing_guards(self, ticker, current_price, hist_df, regime):
        if ticker not in self.holdings: return
        h = self.holdings[ticker]
        atr = h['entry_atr']
        if atr <= 0: return
        
        cfg = REGIME_CONFIG.get(regime, REGIME_CONFIG["SIDEWAYS"])
        pnl_atr = (current_price - h['entry_price']) / atr

        ema10 = ta.ema(hist_df['Close'], length=10)
        if ema10 is not None and not ema10.empty:
            extension = ((current_price - ema10.iloc[-1]) / ema10.iloc[-1]) * 100
            if extension >= cfg["ext_threshold"]:
                new_stop = current_price - (atr * 0.2)
                if new_stop > h['stop_price']:
                    h['stop_price'], h['trailing_active'], h['extension_active'] = new_stop, True, True

        if pnl_atr >= cfg["bolt_trigger"] and not h.get('bolted'):
            lock = h['entry_price'] + (atr * 0.3)
            if lock > h['stop_price']: h['stop_price'], h['bolted'] = lock, True

        if cfg["lock_profit"] and pnl_atr >= cfg["lock_profit"]:
            lock = h['entry_price'] + (atr * 0.8)
            if lock > h['stop_price']: h['stop_price'], h['at_breakeven'], h['profit_locked'] = lock, True, True

        if pnl_atr >= cfg["be_trigger"] and not h.get('at_breakeven'):
            h['stop_price'], h['at_breakeven'] = h['entry_price'] * 1.006, True
            
        if pnl_atr >= 1.0:
            trail_dist = 0.5 if regime == "SIDEWAYS" else 0.7
            new_stop = current_price - (atr * trail_dist)
            if new_stop > h['stop_price']: h['stop_price'], h['trailing_active'] = new_stop, True

    def get_current_equity(self, all_daily, date_dt):
        holding_val = 0
        for t, h in self.holdings.items():
            if t in all_daily and date_dt in all_daily[t].index:
                day_data = all_daily[t].loc[all_daily[t].index == date_dt]
                holding_val += h['qty'] * day_data['Close'].iloc[0] if not day_data.empty else h['qty'] * h['entry_price']
            else:
                holding_val += h['qty'] * h['entry_price']
        return self.balance + holding_val

    def execute_intraday_trade(self, ticker, entry_price, exit_price, stop_price, reason, model_id, date_dt, current_equity, regime):
        """V25: Applies strict Risk Sizing to Intraday Trades"""
        available_slots = self.max_slots - len(self.holdings)
        if available_slots <= 0: return 
        
        current_dd = (self.peak_equity - current_equity) / self.peak_equity
        heat = (BULL_HEAT if regime == "BULL" else BEAR_HEAT) * (2 ** -(current_dd / DRAWDOWN_HALFLIFE) if current_dd > 0 else 1.0)
        if current_dd >= MAX_DRAWDOWN_RECOVERY_MODE: heat = 0.002 
        
        # Risk per share
        risk_rp = entry_price - stop_price
        if risk_rp <= 0: risk_rp = entry_price * 0.03 # Fallback if math fails
        
        equity_at_risk = current_equity * heat
        qty_lots = max(1, int((equity_at_risk / risk_rp) // LOT_SIZE))
        
        max_power = self.balance / available_slots
        max_lots = int(max_power // (entry_price * LOT_SIZE * (1 + FEE_BUY)))
        
        # Take the smaller of: The risk-allowed size, OR the cash-allowed size
        qty_lots = min(qty_lots, max_lots)
        if qty_lots < 1: return
        
        cost = qty_lots * LOT_SIZE * entry_price
        revenue = qty_lots * LOT_SIZE * exit_price
        fee_buy, fee_sell = cost * FEE_BUY, revenue * FEE_SELL
        
        net_pnl_rp = revenue - cost - fee_buy - fee_sell
        pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        
        self.balance += net_pnl_rp
        self.history.append({"date": date_dt, "ticker": ticker, "model": model_id, "pnl": pnl_pct, "pnl_rp": net_pnl_rp, "reason": reason})
        
        m_id = model_id.split('_')[0]
        if m_id not in self.model_stats: self.model_stats[m_id] = {"trades": 0, "pnl_rp": 0, "wins": 0}
        self.model_stats[m_id]["trades"] += 1
        self.model_stats[m_id]["pnl_rp"] += net_pnl_rp
        if net_pnl_rp > 0: self.model_stats[m_id]["wins"] += 1

    def execute_buy(self, ticker, exec_price, day_low, model_id, score, date_dt, daily_df, current_equity, regime, ihsg_micro_trend):
        current_dd = (self.peak_equity - current_equity) / self.peak_equity
        cfg = REGIME_CONFIG.get(regime, REGIME_CONFIG["SIDEWAYS"])
        
        base_threshold = M9_BASE_THRESHOLD + (1.0 if current_dd > 0.05 else 0)
        if score < base_threshold: return "VETO_SCORE"
        
        if model_id.startswith('M3') or model_id.startswith('M4') or score >= 17.5: 
            final_price = exec_price * (1 + MARKET_SLIPPAGE_BETA)
        else:
            limit_price = exec_price * (1 - LIMIT_ENTRY_DISCOUNT)
            if day_low > limit_price: return "VETO_FILL"
            final_price = limit_price
            
        adv, atr = self.calculate_adv_atr(daily_df, date_dt)
        if atr <= 0: return "VETO_ATR"
        
        heat = (BULL_HEAT if regime == "BULL" else BEAR_HEAT) * (2 ** -(current_dd / DRAWDOWN_HALFLIFE) if current_dd > 0 else 1.0)
        if current_dd >= MAX_DRAWDOWN_RECOVERY_MODE: heat = 0.002 
        if not ihsg_micro_trend: heat *= 0.5
            
        # V25 FIX: Use the Regime Stop ATR for all swing models. M4 needs breathing room!
        stop_dist_rp = atr * cfg["stop_atr"]
        
        equity_at_risk = current_equity * heat
        qty_lots = max(1, int((equity_at_risk / stop_dist_rp) // LOT_SIZE))
        
        max_power = self.balance / (self.max_slots - len(self.holdings))
        max_lots = int(max_power // (final_price * LOT_SIZE * (1 + FEE_BUY)))
        qty_lots = min(qty_lots, max_lots)
        
        if qty_lots <= 0: return "VETO_CASH"
        trade_value = qty_lots * LOT_SIZE * final_price
        if adv > 0 and trade_value > (adv * LIQUIDITY_MAX_PARTICIPATION): return "VETO_LIQ"

        self.balance -= (trade_value * (1 + FEE_BUY))
        self.holdings[ticker] = {
            "entry_price": final_price, "qty": qty_lots * LOT_SIZE, "model": model_id, 
            "date": date_dt, "stop_price": final_price - stop_dist_rp, "entry_atr": atr,
            "nominal_cost": trade_value
        }
        return "SUCCESS"

    def execute_sell(self, ticker, raw_price, reason, date_dt):
        if ticker not in self.holdings: return
        h = self.holdings[ticker]
        revenue = (h['qty'] * raw_price) * (1 - FEE_SELL)
        pnl_rp = revenue - (h['nominal_cost'] * (1 + FEE_BUY))
        
        self.balance += revenue
        self.history.append({"date": date_dt, "ticker": ticker, "model": h['model'], "pnl": ((raw_price - h['entry_price']) / h['entry_price']) * 100, "pnl_rp": pnl_rp, "reason": reason})
        
        m_id = h['model'].split('_')[0]
        if m_id not in self.model_stats: self.model_stats[m_id] = {"trades": 0, "pnl_rp": 0, "wins": 0}
        self.model_stats[m_id]["trades"] += 1
        self.model_stats[m_id]["pnl_rp"] += pnl_rp
        if pnl_rp > 0: self.model_stats[m_id]["wins"] += 1
        del self.holdings[ticker]

def run_simulation(max_slots):
    daily_univ, daily_ihsg = load_daily_data()
    intraday_univ = load_intraday_data()
    
    if not daily_univ or not intraday_univ:
        print(f"{RED}❌ Required cache files missing.{RESET}")
        return None

    intraday_dates = set()
    for t, df in intraday_univ.items(): intraday_dates.update(df.index.date)
    sorted_dates = sorted([pd.to_datetime(d) for d in intraday_dates])

    pm = HardenedPortfolioManager(max_slots)
    m1, m2, m3, m4, m5 = M1(), M2(), M3(), M4(), M5()
    m6, m7, m8, m9 = M6(), M7(), M8(), M9(max_slots)
    diagnostic_count = 0

    for idx, today_dt in enumerate(sorted_dates):
        if idx == 0: continue
        yest_dt = sorted_dates[idx-1]
        
        ihsg_hist = daily_ihsg.loc[daily_ihsg.index <= yest_dt]['Close']
        if len(ihsg_hist) < 50: continue 
        
        current_regime = m1.detect_regime(ihsg_hist)
        ihsg_micro_trend = ihsg_hist.iloc[-1] > ta.ema(ihsg_hist, length=5).iloc[-1]

        ihsg_panic_veto = False
        if today_dt in daily_ihsg.index:
            if ((daily_ihsg.loc[daily_ihsg.index == today_dt]['Open'].iloc[0] - ihsg_hist.iloc[-1]) / ihsg_hist.iloc[-1]) < -0.005: 
                ihsg_panic_veto = True

        current_equity = pm.get_current_equity(daily_univ, today_dt)
        if current_equity > pm.peak_equity: pm.peak_equity = current_equity
        cfg = REGIME_CONFIG.get(current_regime, REGIME_CONFIG["SIDEWAYS"])

        # 1. HOLDINGS MAINTENANCE (Swing Stops Only)
        to_sell = []
        for t, h in pm.holdings.items():
            if t in daily_univ and today_dt in daily_univ[t].index:
                day_df = daily_univ[t].loc[daily_univ[t].index == today_dt]
                if not day_df.empty:
                    pm.update_trailing_guards(t, day_df['Close'].iloc[0], daily_univ[t].loc[daily_univ[t].index <= today_dt], current_regime)
                    if day_df['Low'].iloc[0] <= h['stop_price']:
                        reason = "STOP (BOLT)" if h.get('bolted') else "STOP (SL)"
                        to_sell.append((t, h['stop_price'], reason))
                    elif (today_dt - h['date']).days >= cfg["time_exit"] and day_df['Close'].iloc[0] < day_df['Open'].iloc[0]:
                        to_sell.append((t, day_df['Close'].iloc[0], f"TIME ({current_regime})"))
        for t, p, r in to_sell: pm.execute_sell(t, p, r, today_dt)

        # 2. SCAN & EVALUATE
        raw_signals = []
        for t in daily_univ.keys():
            if t == '^JKSE' or t not in intraday_univ: continue
            
            hist_df = daily_univ[t].loc[daily_univ[t].index <= yest_dt]
            if len(hist_df) >= 60:
                c, v, o, h, l = hist_df['Close'], hist_df['Volume'], hist_df['Open'], hist_df['High'], hist_df['Low']
                
                if m1.evaluate(close_prices=c, volume_series=v, market_index_series=ihsg_hist): 
                    raw_signals.append({'ticker': t, 'model': 'M1_Trend', 'raw_score': max(0, 100 - (m1.get_proximity(c) * 5))}) 
                if m2.evaluate(close_prices=c, volume_series=v, open_prices=o, low_prices=l, high_prices=h, market_index_series=ihsg_hist): 
                    raw_signals.append({'ticker': t, 'model': 'M2_Revert', 'raw_score': min(100, m2.get_elasticity_score(c) * 15)})
                if m3.evaluate(close_prices=c, volume_series=v, high_prices=h, low_prices=l, market_index_series=ihsg_hist): 
                    raw_signals.append({'ticker': t, 'model': 'M3_Breakout', 'raw_score': min(100, m3.get_breakout_strength(c, v) * 25)})
                if m4.evaluate(close_prices=c, volume_series=v, open_prices=o, high_prices=h, market_index_series=ihsg_hist): 
                    raw_signals.append({'ticker': t, 'model': 'M4_Alpha', 'raw_score': min(100, max(0, m4.get_alpha_score(c, ihsg_hist) * 10))})

            ihist = intraday_univ[t].loc[intraday_univ[t].index.date <= yest_dt.date()]
            if len(ihist) >= 20:
                is_m6, _ = m6.evaluate(ihist)
                if is_m6: raw_signals.append({'ticker': t, 'model': 'M6_HighBeta', 'raw_score': 35.0})
                is_m7, _ = m7.evaluate(t, ihist)
                if is_m7: raw_signals.append({'ticker': t, 'model': 'M7_Washout', 'raw_score': 35.0})
                is_m8, _ = m8.evaluate(t, ihist)
                if is_m8: raw_signals.append({'ticker': t, 'model': 'M8_Camarilla', 'raw_score': 35.0})

        # 3. M9 TOURNAMENT
        ranked = m9.rank_signals(raw_signals, current_regime)
        picks = m9.manage_exposure(pm.holdings, ranked)
        
        if diagnostic_count < 5 and ranked:
            current_dd = (pm.peak_equity - current_equity) / pm.peak_equity
            print(f"{GRAY}[DIAGNOSTIC {today_dt.strftime('%Y-%m-%d')}] DD: {current_dd*100:.1f}% | Regime: {current_regime} | Candidates: {len(ranked)}{RESET}")
            diagnostic_count += 1

        # 4. EXECUTION (Swing and Intraday Simulators)
        if not ihsg_panic_veto:
            for p in picks:
                t, m_id = p['ticker'], p['model']
                itoday = intraday_univ[t].loc[intraday_univ[t].index.date == today_dt.date()]
                ihist = intraday_univ[t].loc[intraday_univ[t].index.date <= yest_dt.date()]
                if itoday.empty: continue
                
                # M5 Shield
                is_trap, _ = m5.evaluate(itoday, ihist)
                if is_trap: continue
                
                if m_id in ['M6_HighBeta', 'M7_Washout', 'M8_Camarilla']:
                    target_p, stop_p, entry_p = None, None, None
                    start_time = itoday.index[0]
                    
                    if m_id == 'M6_HighBeta':
                        m15_bars = itoday.between_time('09:00', '09:14')
                        if not m15_bars.empty:
                            m15_high = m15_bars['High'].max()
                            risk = m15_high - m15_bars['Low'].min()
                            if risk > 0:
                                entry_p = m15_high * 1.001
                                stop_p = m15_bars['Low'].min()
                                target_p = m15_high + (risk * getattr(m6, 'rr_target', 1.0))
                                start_time = m15_bars.index[-1] + pd.Timedelta(minutes=5)
                    elif m_id == 'M7_Washout':
                        entry_p = itoday['Open'].iloc[0] * (1 - (getattr(m7, 'drop_req', 3.0) / 100))
                        stop_p = entry_p * (1 - (getattr(m7, 'sl_buffer', 1.5) / 100))
                        target_p = itoday['Open'].iloc[0]
                    elif m_id == 'M8_Camarilla':
                        _, m8_plan = m8.evaluate(t, ihist)
                        if m8_plan and 'Buy_Zone' in m8_plan:
                            entry_p = m8_plan['Buy_Zone']
                            stop_p = m8_plan['Cut_Loss']
                            target_p = m8_plan['Target']
                            if itoday['Open'].iloc[0] < entry_p: entry_p = None

                    if entry_p and stop_p:
                        trading_bars = itoday.loc[start_time:]
                        in_trade = False
                        for _, row in trading_bars.iterrows():
                            if not in_trade:
                                if m_id == 'M6_HighBeta' and row['High'] > entry_p: in_trade = True
                                elif m_id in ['M7_Washout', 'M8_Camarilla'] and row['Low'] <= entry_p: in_trade = True
                                
                                if in_trade and row['Low'] <= stop_p: 
                                    pm.execute_intraday_trade(t, entry_p, stop_p, stop_p, "STOP LOSS", m_id, today_dt, current_equity, current_regime)
                                    in_trade = False
                                    break
                            else:
                                if row['High'] >= target_p:
                                    pm.execute_intraday_trade(t, entry_p, target_p, stop_p, "TARGET HIT", m_id, today_dt, current_equity, current_regime)
                                    in_trade = False
                                    break
                                elif row['Low'] <= stop_p:
                                    pm.execute_intraday_trade(t, entry_p, stop_p, stop_p, "STOP LOSS", m_id, today_dt, current_equity, current_regime)
                                    in_trade = False
                                    break
                        if in_trade:
                            pm.execute_intraday_trade(t, entry_p, trading_bars['Close'].iloc[-1], stop_p, "EOD EXIT", m_id, today_dt, current_equity, current_regime)
                else:
                    pm.execute_buy(t, itoday['Open'].iloc[0], itoday['Low'].min(), m_id, p.get('final_score', 0), today_dt, daily_univ[t], current_equity, current_regime, ihsg_micro_trend)

    return pm

if __name__ == "__main__":
    print(f"\n{MAGENTA}🧪 WINTRA GAUNTLET V25: THE RISK PARITY ENGINE{RESET}")
    print(f"{GRAY}Filters: Risk-Sized Intraday Simulator | Restored Swing Stop Limits{RESET}\n")
    
    pm = run_simulation(4) 
    
    if pm:
        final_equity = pm.balance
        for t, h in pm.holdings.items():
            final_equity += h['qty'] * h['entry_price'] 
            
        ret = ((final_equity - STARTING_BALANCE) / STARTING_BALANCE) * 100
        
        print("─"*85)
        print(f"💰 {CYAN}FINAL RESULTS (V25):{RESET}")
        print(f"Ending Balance   : Rp {final_equity:,.0f}")
        print(f"Total Return     : {GREEN if ret > 0 else RED}{ret:+.2f}%{RESET}")
        print(f"Total Trades     : {len(pm.history)}")
        print("─"*85)
        if pm.model_stats:
            for m, s in pm.model_stats.items():
                avg_pnl = s['pnl_rp'] / s['trades'] if s['trades'] > 0 else 0
                wr = (s['wins']/s['trades']*100) if s['trades'] > 0 else 0
                print(f" {m:<12} | Win Rate: {GREEN if wr > 40 else YELLOW}{wr:>5.1f}%{RESET} | Avg Rp/Trade: {GREEN if avg_pnl > 0 else RED}Rp {avg_pnl:>+10,.0f}{RESET}")