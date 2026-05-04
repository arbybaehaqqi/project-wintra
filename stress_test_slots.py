import os
import pandas as pd
import numpy as np
import json
from datetime import datetime
import pandas_ta as ta

# 1. SYNCED IMPORTS (Production Registry)
from core.models.m1_trend import TrendModel as M1
from core.models.m2_revert import RevertModel as M2
from core.models.m3_breakout import BreakoutModel as M3
from core.models.m4_leadership import LeadershipModel as M4
from core.models.m5_defensive import DefensiveModel as M5
from core.models.m9_controller import PortfolioController as M9

# --- GAUNTLET V19: THE CLUSTER IGNITION ---
STARTING_BALANCE = 100_000_000 
LOT_SIZE = 100
FEE_BUY = 0.0015                
FEE_SELL = 0.0025               
LIMIT_ENTRY_DISCOUNT = 0.0020   
MARKET_SLIPPAGE_BETA = 0.0015   
LIQUIDITY_MAX_PARTICIPATION = 0.05  

# Risk Calibration
M9_BASE_THRESHOLD = 14.5        # Raised for V19 selectivity
BULL_HEAT = 0.010               
BEAR_HEAT = 0.003               

# Dynamic Shielding
DRAWDOWN_HALFLIFE = 0.08        
MAX_DRAWDOWN_RECOVERY_MODE = 0.15 

# Adaptive Parameters per Regime
REGIME_CONFIG = {
    "BULL": {
        "stop_atr": 2.5, 
        "ext_threshold": 12.0, 
        "time_exit": 4, 
        "be_trigger": 0.6,
        "bolt_trigger": 0.8,    # Bolt at 0.8x ATR
        "lock_profit": False,
        "vol_accel": 1.1,
        "cluster_min": 1        # Bull doesn't need clusters
    },
    "SIDEWAYS": {
        "stop_atr": 1.7, 
        "ext_threshold": 8.0, 
        "time_exit": 2, 
        "be_trigger": 0.4,
        "bolt_trigger": 0.7,    # Bolt at 0.7x ATR
        "lock_profit": 1.0,     
        "vol_accel": 1.3,
        "cluster_min": 3        # Must see 3+ signals to lower threshold
    },
    "BEAR": {
        "stop_atr": 1.5, 
        "ext_threshold": 6.0, 
        "time_exit": 1, 
        "be_trigger": 0.4,
        "bolt_trigger": 0.6,
        "lock_profit": 0.8,
        "vol_accel": 1.5,
        "cluster_min": 5        # Needs extreme clustering in Bear
    }
}

CACHE_DIR = "core/data/intraday_cache"

# ANSI Colors
CYAN, GREEN, YELLOW, RED, MAGENTA, GRAY, RESET = "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[95m", "\033[90m", "\033[0m"

class HardenedPortfolioManager:
    def __init__(self, max_slots):
        self.max_slots = max_slots
        self.balance = STARTING_BALANCE
        self.holdings = {} 
        self.history = []
        self.model_stats = {}
        self.peak_equity = STARTING_BALANCE

    def calculate_adv_atr(self, ticker_data, date):
        try:
            all_dates = sorted([d for d in ticker_data.keys() if d < date])
            if len(all_dates) < 5: return 0, 0
            lookback = 14 if len(all_dates) >= 14 else len(all_dates)
            df_list = [ticker_data[d] for d in all_dates[-lookback:]]
            combined = pd.concat(df_list)
            atr_series = ta.atr(combined['High'], combined['Low'], combined['Close'], length=lookback)
            atr_val = atr_series.iloc[-1] if (atr_series is not None and not atr_series.empty) else 0
            daily_vols = [ticker_data[d]['Close'].iloc[-1] * ticker_data[d]['Volume'].sum() for d in all_dates[-lookback:]]
            return np.mean(daily_vols), atr_val
        except: return 0, 0

    def update_trailing_guards(self, ticker, current_price, ticker_df, regime):
        if ticker not in self.holdings: return
        h = self.holdings[ticker]
        atr = h['entry_atr']
        if atr <= 0: return
        
        cfg = REGIME_CONFIG.get(regime, REGIME_CONFIG["SIDEWAYS"])
        pnl_atr = (current_price - h['entry_price']) / atr

        # 1. Adaptive Extension Check
        ema10_series = ta.ema(ticker_df['Close'], length=10)
        if ema10_series is not None and not ema10_series.empty:
            curr_ema = ema10_series.iloc[-1]
            extension = ((current_price - curr_ema) / curr_ema) * 100
            if extension >= cfg["ext_threshold"]:
                new_stop = current_price - (atr * 0.2)
                if new_stop > h['stop_price']:
                    h['stop_price'] = new_stop
                    h['trailing_active'] = True
                    h['extension_active'] = True

        # 2. V19: The Safety Bolt (Entry + 0.2 ATR)
        if pnl_atr >= cfg["bolt_trigger"] and not h.get('bolted'):
            lock_level = h['entry_price'] + (atr * 0.2)
            if lock_level > h['stop_price']:
                h['stop_price'] = lock_level
                h['bolted'] = True

        # 3. Dynamic Profit Lock
        if cfg["lock_profit"] and pnl_atr >= cfg["lock_profit"]:
            lock_level = h['entry_price'] + (atr * 0.5)
            if lock_level > h['stop_price']:
                h['stop_price'] = lock_level
                h['at_breakeven'] = True
                h['profit_locked'] = True

        # 4. Protective Breakeven
        if pnl_atr >= cfg["be_trigger"] and not h.get('at_breakeven'):
            h['stop_price'] = h['entry_price'] * 1.006 
            h['at_breakeven'] = True
            
        # 5. Trailing Profit Stop
        if pnl_atr >= 1.0:
            trail_dist = 0.5 if regime == "SIDEWAYS" else 0.7
            new_stop = current_price - (atr * trail_dist)
            if new_stop > h['stop_price']:
                h['stop_price'] = new_stop
                h['trailing_active'] = True

    def get_current_equity(self, all_data, date):
        holding_val = 0
        for t, h in self.holdings.items():
            if t in all_data and date in all_data[t]:
                holding_val += h['qty'] * all_data[t][date]['Close'].iloc[-1]
            else:
                holding_val += h['qty'] * h['entry_price']
        return self.balance + holding_val

    def execute_buy(self, ticker, day_open, day_low, model_id, score, date, ticker_history_dict, current_equity, regime, cluster_count):
        current_dd = (self.peak_equity - current_equity) / self.peak_equity
        cfg = REGIME_CONFIG.get(regime, REGIME_CONFIG["SIDEWAYS"])
        
        # V19 Cluster Threshold Adjustment
        base_threshold = M9_BASE_THRESHOLD + (1.0 if current_dd > 0.05 else 0)
        if cluster_count < cfg["cluster_min"]:
            base_threshold += 2.0 # Penalty for isolated signals
        
        if score < base_threshold: return "VETO_SCORE"
        
        # Entry Selection
        if score >= 17.5: 
            execution_price = day_open * (1 + MARKET_SLIPPAGE_BETA)
        else:
            limit_price = day_open * (1 - LIMIT_ENTRY_DISCOUNT)
            if day_low > limit_price: return "VETO_FILL"
            execution_price = limit_price
            
        adv, atr = self.calculate_adv_atr(ticker_history_dict, date)
        if atr <= 0: return "VETO_ATR"
        
        # HEAT SHIELD
        base_heat = BULL_HEAT if regime == "BULL" else BEAR_HEAT
        decay_factor = 2 ** -(current_dd / DRAWDOWN_HALFLIFE) if current_dd > 0 else 1.0
        heat = base_heat * decay_factor
        if current_dd >= MAX_DRAWDOWN_RECOVERY_MODE: heat = 0.002 
            
        stop_dist_rp = atr * cfg["stop_atr"]
        equity_at_risk = current_equity * heat
        
        qty_lots = int((equity_at_risk / stop_dist_rp) // LOT_SIZE)
        if qty_lots < 1: qty_lots = 1
        
        available_slots = self.max_slots - len(self.holdings)
        max_power = self.balance / available_slots
        max_lots = int(max_power // (execution_price * LOT_SIZE * (1 + FEE_BUY)))
        qty_lots = min(qty_lots, max_lots)
        
        if qty_lots <= 0: return "VETO_CASH"
        trade_value = qty_lots * LOT_SIZE * execution_price
        if adv > 0 and trade_value > (adv * LIQUIDITY_MAX_PARTICIPATION): return "VETO_LIQ"

        self.balance -= (trade_value * (1 + FEE_BUY))
        self.holdings[ticker] = {
            "entry_price": execution_price, "qty": qty_lots * LOT_SIZE, "model": model_id, 
            "date": date, "stop_price": execution_price - stop_dist_rp, "entry_atr": atr,
            "nominal_cost": trade_value
        }
        return "SUCCESS"

    def execute_sell(self, ticker, raw_price, reason, date):
        if ticker not in self.holdings: return
        h = self.holdings[ticker]
        revenue = (h['qty'] * raw_price) * (1 - FEE_SELL)
        pnl_rp = revenue - (h['nominal_cost'] * (1 + FEE_BUY))
        pnl_pct = ((raw_price - h['entry_price']) / h['entry_price']) * 100
        
        self.balance += revenue
        self.history.append({"date": date, "ticker": ticker, "model": h['model'], "pnl": pnl_pct, "pnl_rp": pnl_rp, "reason": reason})
        
        m_id = h['model']
        if m_id not in self.model_stats: self.model_stats[m_id] = {"trades": 0, "pnl_rp": 0, "wins": 0}
        self.model_stats[m_id]["trades"] += 1
        self.model_stats[m_id]["pnl_rp"] += pnl_rp
        if pnl_rp > 0: self.model_stats[m_id]["wins"] += 1
        del self.holdings[ticker]

def run_simulation(max_slots, all_data, sorted_dates):
    pm = HardenedPortfolioManager(max_slots)
    m1, m2, m3, m4, m5, m9 = M1(), M2(), M3(), M4(), M5(), M9(max_slots)
    diagnostic_count = 0

    for idx, today in enumerate(sorted_dates):
        if idx == 0: continue
        yesterday = sorted_dates[idx-1]
        
        ihsg_df_yest = all_data.get('^JKSE', {}).get(yesterday)
        ihsg_df_today = all_data.get('^JKSE', {}).get(today)
        
        ihsg_morning = ihsg_df_yest['Close'].iloc[-1] if ihsg_df_yest is not None else None
        current_regime = m1.detect_regime(ihsg_morning)
        
        ihsg_panic_veto = False
        if ihsg_df_today is not None and ihsg_morning:
            ihsg_open = ihsg_df_today['Open'].iloc[0]
            if ((ihsg_open - ihsg_morning) / ihsg_morning) < -0.005: 
                ihsg_panic_veto = True

        current_equity = pm.get_current_equity(all_data, today)
        if current_equity > pm.peak_equity: pm.peak_equity = current_equity
        cfg = REGIME_CONFIG.get(current_regime, REGIME_CONFIG["SIDEWAYS"])

        # 1. EXIT LOGIC
        to_sell = []
        for t, h in pm.holdings.items():
            if today in all_data[t]:
                day_df = all_data[t][today]
                pm.update_trailing_guards(t, day_df['Close'].iloc[-1], day_df, current_regime)
                
                if day_df['Low'].min() <= h['stop_price']:
                    if h.get('bolted'): reason = "STOP (BOLT)"
                    elif h.get('profit_locked'): reason = "STOP (LOCK)"
                    elif h.get('extension_active'): reason = "STOP (EXTENSION)"
                    else: reason = "STOP (SL)"
                    to_sell.append((t, h['stop_price'], reason))
                elif (today - h['date']).days >= cfg["time_exit"]:
                    to_sell.append((t, day_df['Close'].iloc[-1], f"TIME ({current_regime})"))
                    
        for t, p, r in to_sell: pm.execute_sell(t, p, r, today)

        # 2. SCANNING
        raw_signals = []
        m1_cluster_count = 0
        for t, ticker_days in all_data.items():
            if t == '^JKSE' or yesterday not in ticker_days or today not in ticker_days: continue
            y_df = ticker_days[yesterday]
            c, v, o, h, l = y_df['Close'], y_df['Volume'], y_df['Open'], y_df['High'], y_df['Low']
            
            rsi_series = ta.rsi(c, length=14)
            ema10_series = ta.ema(c, length=10)
            adx_series = ta.adx(h, l, c, length=14)
            
            if m5.evaluate(ticker_days[today], ticker_days[yesterday])[0]: continue

            if m1.evaluate(c, v, ihsg_morning):
                vol_sma5 = v.rolling(5).mean().iloc[-1]
                curr_rsi = rsi_series.iloc[-1] if rsi_series is not None else 50
                curr_adx = adx_series['ADX_14'].iloc[-1] if adx_series is not None else 0
                ema_slope = (ema10_series.iloc[-1] - ema10_series.iloc[-2]) if len(ema10_series) > 1 else 0
                
                # ADX Floor raised to 22 for V19
                if current_regime != "BULL" and curr_adx < 22: continue
                if v.iloc[-1] < (vol_sma5 * cfg["vol_accel"]): continue
                
                if curr_rsi < 68 and ema_slope > 0:
                    raw_signals.append({'ticker': t, 'model': 'M1_Trend', 'raw_score': max(0, 100 - (m1.get_proximity(c) * 12))}) 
                    m1_cluster_count += 1
            
            if m2.evaluate(c, v, o, l, h, ihsg_morning):
                raw_signals.append({'ticker': t, 'model': 'M2_Revert', 'raw_score': m2.get_elasticity_score(c) * 10})
            if m3.evaluate(c, v, h, l, ihsg_morning):
                raw_signals.append({'ticker': t, 'model': 'M3_Breakout', 'raw_score': m3.get_breakout_strength(c, v) * 8})
            if m4.evaluate(c, v, o, h, ihsg_morning):
                raw_signals.append({'ticker': t, 'model': 'M4_Alpha', 'raw_score': m4.get_alpha_score(c, ihsg_morning)})

        # 3. TOURNAMENT
        ranked = m9.rank_signals(raw_signals, current_regime)
        picks = m9.manage_exposure(pm.holdings, ranked)
        
        if diagnostic_count < 5 and ranked:
            current_dd = (pm.peak_equity - current_equity) / pm.peak_equity
            print(f"{GRAY}[DIAGNOSTIC {today}] DD: {current_dd*100:.1f}% | Cluster: {m1_cluster_count} | Ranked: {len(ranked)} | High Score: {ranked[0]['final_score']:.1f}{RESET}")
            diagnostic_count += 1

        if not ihsg_panic_veto:
            for p in picks:
                t_day = all_data[p['ticker']][today]
                status = pm.execute_buy(p['ticker'], t_day['Open'].iloc[0], t_day['Low'].min(), p['model'], p.get('final_score', 0), today, all_data[p['ticker']], current_equity, current_regime, m1_cluster_count)
                if status != "SUCCESS" and diagnostic_count < 10:
                    print(f" {GRAY}>> Execution {p['ticker']}: {status}{RESET}")

    return pm

if __name__ == "__main__":
    print(f"\n{MAGENTA}🧪 WINTRA GAUNTLET V19: THE CLUSTER IGNITION{RESET}")
    print(f"{GRAY}Filters: Sector Cluster (3+) | Safety Bolt (0.7x ATR) | ADX Floor (22){RESET}\n")
    
    all_data, all_dates = {}, set()
    for f in [f for f in os.listdir(CACHE_DIR) if f.endswith(".csv")]:
        ticker = f.split("_")[0]
        df = pd.read_csv(os.path.join(CACHE_DIR, f), parse_dates=['Datetime'])
        if df['Datetime'].dt.hour.iloc[0] < 7: df['Datetime'] += pd.Timedelta(hours=7)
        df.set_index('Datetime', inplace=True)
        all_data[ticker] = {d: g for d, g in df.groupby(df.index.date)}
        all_dates.update(all_data[ticker].keys())
    
    sorted_dates = sorted(list(all_dates))
    pm = run_simulation(3, all_data, sorted_dates)
    final_equity = pm.get_current_equity(all_data, sorted_dates[-1])
    ret = ((final_equity - STARTING_BALANCE) / STARTING_BALANCE) * 100
    
    print("─"*85)
    print(f"💰 {CYAN}FINAL RESULTS (V19):{RESET}")
    print(f"Ending Balance   : Rp {final_equity:,.0f}")
    print(f"Total Return     : {GREEN if ret > 0 else RED}{ret:+.2f}%{RESET}")
    print(f"Total Trades     : {len(pm.history)}")
    print("─"*85)
    if pm.model_stats:
        for m, s in pm.model_stats.items():
            avg_pnl = s['pnl_rp'] / s['trades']
            wr = (s['wins']/s['trades']*100)
            print(f" {m:<12} | Win Rate: {GREEN if wr > 40 else YELLOW}{wr:>5.1f}%{RESET} | Avg Rp/Trade: {GREEN if avg_pnl > 0 else RED}Rp {avg_pnl:>+10,.0f}{RESET}")
