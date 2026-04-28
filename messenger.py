import yfinance as yf
import pandas as pd
import warnings
import requests

warnings.filterwarnings('ignore') # Suppress yfinance warnings

class WintraEngine:
    def __init__(self):
        self.universe = [
            'BBCA.JK', 'BBRI.JK', 'BMRI.JK', 'BBNI.JK', 'AMMN.JK', 
            'TLKM.JK', 'ASII.JK', 'MEDC.JK', 'ADRO.JK', 'INCO.JK', 
            'BRPT.JK', 'PGEO.JK', 'GOTO.JK', 'BREN.JK', 'UNTR.JK'
        ]
        
        # MODEL 4 MACRO TICKERS (Yahoo Finance Symbols)
        self.macro_tickers = {
            'Oil': 'BZ=F',       # Brent Crude Futures
            'USDIDR': 'IDR=X',   # USD to IDR Exchange Rate
            'Gold': 'GC=F'       # Gold Futures
        }
        
    def fetch_data(self):
        print(f"📡 Fetching data for {len(self.universe)} stocks + Macro Indicators...")
        all_tickers = self.universe + list(self.macro_tickers.values())
        data = yf.download(all_tickers, period="3mo", interval="1d", group_by='ticker', progress=False)
        return data

    def calculate_indicators(self, df):
        """Calculates MA5, MA20, RSI, and Volume metrics."""
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA50'] = df['Close'].rolling(window=50).mean()
        df['Vol_20'] = df['Volume'].rolling(window=20).mean()
        
        df['BB_Mid'] = df['MA20']
        df['BB_Upper'] = df['BB_Mid'] + 2 * df['Close'].rolling(window=20).std()
        df['BB_Lower'] = df['BB_Mid'] - 2 * df['Close'].rolling(window=20).std()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        return df.iloc[-1]

    def run_models(self):
        raw_data = self.fetch_data()
        
        # --- PRE-COMPUTE MODEL 4 (MACRO SIGNALS) ---
        macro_signals = {}
        try:
            oil_pct = raw_data[self.macro_tickers['Oil']]['Close'].pct_change().iloc[-1]
            gold_pct = raw_data[self.macro_tickers['Gold']]['Close'].pct_change().iloc[-1]
            idr_pct = raw_data[self.macro_tickers['USDIDR']]['Close'].pct_change().iloc[-1]
            
            macro_signals['MEDC.JK'] = oil_pct > 0.015   
            macro_signals['AMMN.JK'] = gold_pct > 0.015  
            macro_signals['ADRO.JK'] = idr_pct > 0.005   
        except Exception as e:
            print(f"⚠️ Macro fetch warning: {e}")

        results = []

        for ticker in self.universe:
            try:
                df = raw_data[ticker].dropna()
                if df.empty or len(df) < 50:
                    continue
                
                latest = self.calculate_indicators(df)
                
                # --- APPLYING THE 4 MODELS ---
                trend_flag = bool((latest['MA5'] > latest['MA20']) and (latest['Close'] > latest['MA50']) and (50 < latest['RSI'] < 70))
                reversion_flag = bool((latest['RSI'] < 30) and (latest['Close'] <= latest['BB_Lower'] * 1.01))
                volume_flag = bool(latest['Volume'] > (latest['Vol_20'] * 2.0))
                macro_flag = bool(macro_signals.get(ticker, False))

                if trend_flag or reversion_flag or volume_flag or macro_flag:
                    results.append({
                        'Ticker': ticker.replace('.JK', ''),
                        'Close': round(latest['Close'], 0),
                        'Model_1_Trend': trend_flag,
                        'Model_2_Revert': reversion_flag,
                        'Model_3_Volume': volume_flag,
                        'Model_4_Macro': macro_flag,
                        'Confluence': sum([trend_flag, reversion_flag, volume_flag, macro_flag])
                    })
            except Exception as e:
                print(f"Error processing {ticker}: {e}")
                
        return pd.DataFrame(results)

    def format_telegram_message(self, df):
        """Optimized UI for Project Wintra Report."""
        if df.empty:
            return "📭 *PROJECT WINTRA: DAILY SCAN*\n\nMarket seems quiet. No setups detected that meet our criteria for today."

        # Header with clean styling
        date_str = pd.Timestamp.now(tz='Asia/Jakarta').strftime('%d %b %Y | %H:%M')
        header = f"🏆 *PROJECT WINTRA* 🏆\n`REPORT: {date_str} WIB`\n"
        divider = "────────────────────\n"
        
        msg = header + divider

        # 1. High Conviction Area (Top Priority)
        confluence_df = df[df['Confluence'] >= 2].sort_values('Confluence', ascending=False)
        if not confluence_df.empty:
            msg += "🔥 *HIGH CONVICTION ZONE*\n"
            for _, row in confluence_df.iterrows():
                # Using 🎯 for top picks
                msg += f"🎯 `{row['Ticker']:<6}` ➜ `Rp {int(row['Close']):>6}`\n"
            msg += divider

        # 2. Sectional Reports
        model_sections = [
            ('Model_1_Trend', "🟢 *SWING (Trend)*"),
            ('Model_2_Revert', "🔴 *SCALP (Reversion)*"),
            ('Model_3_Volume', "🟣 *WHALE (Volume)*"),
            ('Model_4_Macro', "🛢️ *MACO (Macro)*")
        ]

        for col, title in model_sections:
            subset = df[df[col] == True]
            if not subset.empty:
                msg += f"{title}\n"
                for _, row in subset.iterrows():
                    # Using code blocks for tickers/prices to keep columns straight
                    msg += f"`{row['Ticker']:<6}` ➜ `{int(row['Close']):>6}`\n"
                msg += "\n"

        msg += divider
        msg += "_Stay reliable. Trade with discipline._"
        return msg
    
# --- OUTSIDE THE CLASS: TELEGRAM SENDER ---
def send_telegram_alert(message):
    import os
    # It checks GitHub first, then falls back to your local keys if they aren't found
    BOT_TOKEN = os.getenv('BOT_TOKEN', '8722893288:AAHKabxmDpZqn5XbZ2s5bdoh0QBvCQ7h0F8')
    CHAT_ID = os.getenv('CHAT_ID', '7751541131')
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Telegram alert sent successfully!")
        else:
            print(f"❌ Failed to send Telegram alert: {response.text}")
            print("Make sure you started the chat with your bot first!")
    except Exception as e:
        print(f"❌ Error sending message: {e}")

# --- LOCAL TESTING EXECUTOR ---
if __name__ == "__main__":
    engine = WintraEngine()
    print("🚀 Running Project Wintra Engine...")
    
    report_df = engine.run_models()
    telegram_msg = engine.format_telegram_message(report_df)
    
    print("\n--- MESSAGE PREVIEW ---\n")
    print(telegram_msg)
    print("\n-----------------------\n")
    
    send_telegram_alert(telegram_msg)
