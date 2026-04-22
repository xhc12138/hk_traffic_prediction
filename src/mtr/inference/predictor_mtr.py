import pandas as pd
from typing import Dict, Any
import random
import torch
import numpy as np
from pathlib import Path
import os
import sys

project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(project_root))

from src.mtr.train_delay_risk import MTRDelayRiskGRU
from src.mtr.train_delay_propagation import MTRDelayPropagationModel
from src.utils.config import config

class MTRPredictor:
    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        try:
            torch.zeros(1).to(self.device)
        except RuntimeError:
            self.device = torch.device('cpu')
            
        self.risk_model_path = os.path.join(project_root, "data/models/mtr_delay_risk.pth")
        self.prop_model_path = os.path.join(project_root, "data/models/mtr_delay_propagation.pth")
        
        self.risk_model = self._load_risk_model()
        self.prop_model = self._load_prop_model()
        
        self.seq_len = 10
        print("[MTR] Predictor initialized.")
        
    def _load_risk_model(self):
        try:
            model = MTRDelayRiskGRU().to(self.device)
        except RuntimeError:
            self.device = torch.device('cpu')
            model = MTRDelayRiskGRU().to(self.device)
            
        if os.path.exists(self.risk_model_path):
            model.load_state_dict(torch.load(self.risk_model_path, map_location=self.device, weights_only=True))
            print(f"[MTR] Loaded Risk Model from {self.risk_model_path}")
        else:
            print(f"[MTR] Warning: Risk model not found. Using untrained weights.")
        model.eval()
        return model
        
    def _load_prop_model(self):
        try:
            model = MTRDelayPropagationModel().to(self.device)
        except RuntimeError:
            self.device = torch.device('cpu')
            model = MTRDelayPropagationModel().to(self.device)
            
        if os.path.exists(self.prop_model_path):
            model.load_state_dict(torch.load(self.prop_model_path, map_location=self.device, weights_only=True))
            print(f"[MTR] Loaded Propagation Model from {self.prop_model_path}")
        else:
            print(f"[MTR] Warning: Propagation model not found. Using untrained weights.")
        model.eval()
        return model

    def predict_risk(self, df: pd.DataFrame, mock: bool = True) -> Dict[str, float]:
        """
        Primary Task: Delay Risk Probability (isdelay="Y" probability)
        Returns: {"TCL-OLY": 0.23, ...}
        """
        results = {}
        if df.empty:
            return results
            
        if not mock:
            features = ['up_ttnt_1', 'down_ttnt_1', 'hour', 'day_of_week', 'is_weekend', 'is_peak']
            with torch.no_grad():
                # Prepare batch
                lines_stas = []
                feats_list = []
                for _, row in df.iterrows():
                    key = f"{row['line']}-{row['sta']}"
                    lines_stas.append(key)
                    
                    up_ttnt = float(row.get('up_ttnt_1', 0.0)) / 60.0
                    down_ttnt = float(row.get('down_ttnt_1', 0.0)) / 60.0
                    feat = [up_ttnt, down_ttnt, row.get('hour', 0), row.get('day_of_week', 0), row.get('is_weekend', 0), row.get('is_peak', 0)]
                    feats_list.append(feat)
                
                # Sequence length = 10, pad with copies of current state
                feats_arr = np.array(feats_list) # [N, 6]
                seqs = np.repeat(feats_arr[:, np.newaxis, :], self.seq_len, axis=1) # [N, 10, 6]
                x_tensor = torch.tensor(seqs, dtype=torch.float32).to(self.device)
                
                preds = self.risk_model(x_tensor).cpu().numpy().flatten()
                for key, pred in zip(lines_stas, preds):
                    results[key] = round(float(pred), 4)
            return results

        for _, row in df.iterrows():
            key = f"{row['line']}-{row['sta']}"
            results[key] = round(random.uniform(0.01, 0.99), 2)
        return results

    def predict_propagation(self, df: pd.DataFrame, mock: bool = True) -> Dict[str, Dict[str, Any]]:
        """
        Advanced Task: Delay Duration + Affected Trains
        Returns: {"TCL-OLY": {"duration_mins": 14.8, "affected_trains": 3, "color_code": "yellow"}, ...}
        """
        results = {}
        if df.empty:
            return results
            
        risk_preds = self.predict_risk(df, mock=mock)
        
        if not mock:
            with torch.no_grad():
                lines_stas = []
                feats_list = []
                for _, row in df.iterrows():
                    key = f"{row['line']}-{row['sta']}"
                    lines_stas.append(key)
                    
                    up_ttnt = float(row.get('up_ttnt_1', 0.0)) / 60.0
                    down_ttnt = float(row.get('down_ttnt_1', 0.0)) / 60.0
                    feat = [up_ttnt, down_ttnt, row.get('hour', 0), row.get('day_of_week', 0), row.get('is_weekend', 0), row.get('is_peak', 0)]
                    feats_list.append(feat)
                
                feats_arr = np.array(feats_list)
                # Seq len = 1 for propagation
                seqs = feats_arr[:, np.newaxis, :]
                x_tensor = torch.tensor(seqs, dtype=torch.float32).to(self.device)
                
                preds = self.prop_model(x_tensor).cpu().numpy()
                
                for key, pred in zip(lines_stas, preds):
                    risk = risk_preds.get(key, 0.0)
                    duration = round(float(pred[0]), 1)
                    affected = max(0, int(round(float(pred[1]))))
                    
                    color = "green"
                    if risk > 0.7:
                        color = "red"
                    elif risk > 0.3:
                        color = "yellow"
                        
                    results[key] = {
                        "delay_risk_probability": risk,
                        "delay_duration_minutes": duration,
                        "affected_trains_count": affected,
                        "color_code": color,
                        "up_ttnt": round(up_ttnt * 60, 1),
                        "down_ttnt": round(down_ttnt * 60, 1)
                    }
            return results

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
