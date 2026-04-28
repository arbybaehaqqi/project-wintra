import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Import the Brain from our core module
from core.models import WintraModels

class MorningOrchestrator:
    """
    The Executive Orchestrator for the 08:30 AM Wintra View.
    Bridges raw technical data with tactical market insights.
    """
    def __init__(self):
        load_dotenv() 
        self.data_dir = os.path.join("core", "data")
        self.ticker_file = os.path.join(self.data_dir, "idx80_list.json")
        self.history_file = os.path.join(self.data_dir, "morning_history.json")
        os.makedirs(self.data_dir, exist_ok=True)

    def calculate_delta(self, current_top_5):
        """Standard Delta logic to track momentum shifts."""
        delta_results = {}
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    yesterday_ranks = json.load(f)
            except: yesterday_ranks = {}
        else: yesterday_ranks = {}

        for i, item in enumerate(current_top_5):
            ticker = item['ticker']
            current_rank = i + 1
            prev_rank = yesterday_ranks.get(ticker)
            if prev_rank is None: delta_results[ticker] = "🆕"
            elif current_rank < prev_rank: delta_results[ticker] = f"▲{prev_rank - current_rank}"
            elif current_rank > prev_rank: delta_results[ticker] = f"▼{current_rank - prev_rank}"
            else: delta_results[ticker] = "—"

        # Persistence for tomorrow's run
        today_ranks = {item['ticker']: i + 1 for i, item in enumerate(current_top_5)}
        with open(self.history_file, 'w') as f:
            json.dump(today_ranks, f, indent=4)
        return delta_results

    def generate_insight(self, signals, char):
        """Translates technical signal clusters into professional market commentary."""
        logic_map = {
            'M1': "Strong trend alignment above major EMAs.",
            'M2': "Oversold conditions indicating a technical bounce play.",
            'M3': "Abnormal institutional volume detected (Big Money presence).",
            'M4': "Relative Strength outperformance against the IDX composite."
        }
        
        active_insights = [logic_map[s] for s in signals.split(", ") if s in logic_map]
        narrative = " ".join(active_insights)
        return f"{char}: {narrative}"

    def print_executive_report(self, top_5, deltas):
        """High-contrast professional layout mimicking the Gemini scheduled task."""
        date_str = datetime.now().strftime("%A, %B %d, %Y")
        
        print("\n" + "═"*60)
        print(f"🏛️  WINTRA EXECUTIVE VIEW | PRE-MARKET STRATEGY")
        print(f"Time: 08:30 WIB | Date: {date_str}")
        print(f"Status: 🟢 System Analysis Complete (IDX80+ Universe)")
        print("═"*60)
        
        print("\n🏆 THE TOURNAMENT PODIUM (Top 5 Ranking)")
        print("─"*60)

        medals = ["🥇", "🥈", "🥉", "4th", "5th"]
        
        if not top_5:
            print("⚠️ ADVISORY: Market trend is currently broken. No high-conviction picks.")
        else:
            for i, item in enumerate(top_5):
                t = item['ticker']
                price = f"Rp{item['price']:,.0f}"
                delta = deltas[t]
                
                # Header Line
                print(f"{medals[i]} {t.ljust(6)} ({price.rjust(10)}) | {delta}")
                
                # Signal Meta
                print(f"   ↳ Score: {item['score']} | Signals: {item['signals']}")
                
                # Strategic Insight
                insight = self.generate_insight(item['signals'], item['char'])
                print(f"   ↳ Insight: {insight}")
                print("")
            
        print("─"*60)
        print("📝 TACTICAL VERDICT")
        if top_5:
            primary = top_5[0]['ticker']
            print(f"• Priority: Focus on {primary} for opening strength confirmation.")
            print(f"• Context:  Candidates marked '▲' or '🆕' represent active accumulation.")
            print(f"• Action:   Await 09:50 Audit to verify ARA breakout velocity.")
        else:
            print("• Action:   Preserve capital. Sectoral rotation is currently erratic.")
            
        print("\n" + "═"*60)
        print("💡 Windra Engine: Quantitative analysis complete.")
        print("═"*60 + "\n")

    def execute(self):
        print("⚙️  Wintra Engine starting morning routine...")
        engine = WintraModels(data_path=self.ticker_file)
        
        if not engine.yf_tickers:
            print(f"❌ Error: Could not locate ticker list at {self.ticker_file}")
            return

        # Data processing
        prices, volumes = engine.fetch_daily_data()
        results = engine.run_daily_tournament(prices, volumes)
        
        # Ranking and reporting
        top_5 = results[:5]
        deltas = self.calculate_delta(top_5)
        self.print_executive_report(top_5, deltas)

if __name__ == "__main__":
    orchestrator = MorningOrchestrator()
    orchestrator.execute()