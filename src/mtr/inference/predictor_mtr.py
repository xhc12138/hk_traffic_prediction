import pandas as pd
from typing import Dict, Any
import random

class MTRPredictor:
    def __init__(self):
        # MOCK initialization: Would load PyTorch models here
        self.risk_model_loaded = False
        self.propagation_model_loaded = False
        print("[MTR] Predictor initialized.")

    def predict_risk(self, df: pd.DataFrame, mock: bool = True) -> Dict[str, float]:
        """
        Primary Task: Delay Risk Probability (isdelay="Y" probability)
        Returns: {"TCL-OLY": 0.23, ...}
        """
        results = {}
        for _, row in df.iterrows():
            key = f"{row['line']}-{row['sta']}"
            if mock:
                results[key] = round(random.uniform(0.01, 0.99), 2)
            else:
                # Placeholder for real model inference
                results[key] = 0.0
        return results

    def predict_propagation(self, df: pd.DataFrame, mock: bool = True) -> Dict[str, Dict[str, Any]]:
        """
        Advanced Task: Delay Duration + Affected Trains
        Returns: {"TCL-OLY": {"duration_mins": 14.8, "affected_trains": 3, "color_code": "yellow"}, ...}
        """
        results = {}
        for _, row in df.iterrows():
            key = f"{row['line']}-{row['sta']}"
            
            if mock:
                risk = random.uniform(0.01, 0.99)
                duration = 0.0
                affected = 0
                color = "green"
                
                if risk > 0.7:
                    duration = round(random.uniform(15, 45), 1)
                    affected = random.randint(3, 8)
                    color = "red"
                elif risk > 0.3:
                    duration = round(random.uniform(5, 15), 1)
                    affected = random.randint(1, 3)
                    color = "yellow"
                    
                results[key] = {
                    "delay_risk_probability": round(risk, 2),
                    "delay_duration_minutes": duration,
                    "affected_trains_count": affected,
                    "color_code": color
                }
            else:
                # Placeholder for real model inference
                results[key] = {
                    "delay_risk_probability": 0.0,
                    "delay_duration_minutes": 0.0,
                    "affected_trains_count": 0,
                    "color_code": "green"
                }
                
        return results

# Singleton instance
mtr_predictor = MTRPredictor()
