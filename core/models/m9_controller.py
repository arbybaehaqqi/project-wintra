import pandas as pd
import numpy as np

class PortfolioController:
    """
    Model 9: Portfolio Controller (The General) - Version 1.2
    Role: Capital Allocation, Risk Balancing, and Model Priority.
    """
    
    # Standardized weights for all models across regimes
    REGIME_PRIORITY = {
    "BULL": {
        "M1": 0.55,
        "M3": 0.38,
        "M4": 0.72,
        "M6": 0.65,
    },
    "BEAR": {
        "M2": 0.68,
        "M1": 0.23,
        "M7": 0.68,
    },
    "SIDEWAYS": {
        "M1": 0.23,
        "M4": 0.64,
        "M8": 0.71,
    },
}

    def __init__(self, max_slots=4, max_per_model=2):
        self.max_slots = max_slots
        self.max_per_model = max_per_model
        self.name = "M9_CONTROLLER"

    def rank_signals(self, signals, regime):
        """
        Takes raw signals and applies weights based on the current market regime.
        Standardizes 'DEFENSIVE' from M1 to 'BEAR' logic.
        """
        lookup_regime = "BEAR" if regime in ["BEAR", "DEFENSIVE"] else regime
        priority_map = self.REGIME_PRIORITY.get(lookup_regime, self.REGIME_PRIORITY["SIDEWAYS"])
        
        ranked = []
        for s in signals:
            # Clean the model ID (e.g., M1_Trend -> M1)
            m_id = s['model'].split('_')[0]
            weight = priority_map.get(m_id, 0.0)
            
            if weight > 0:
                s['final_score'] = s['raw_score'] * weight
                ranked.append(s)
            
        return sorted(ranked, key=lambda x: x['final_score'], reverse=True)

    def manage_exposure(self, current_holdings, ranked_candidates):
        """Ensures diversification across models."""
        approved_picks = []
        slots_filled = len(current_holdings)
        model_counts = {}

        for candidate in ranked_candidates:
            if slots_filled >= self.max_slots: break
            
            m_id = candidate['model'].split('_')[0]
            current_m_count = model_counts.get(m_id, 0)
            
            if current_m_count < self.max_per_model:
                approved_picks.append(candidate)
                model_counts[m_id] = current_m_count + 1
                slots_filled += 1
                
        return approved_picks
