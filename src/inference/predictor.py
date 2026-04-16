import torch
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import os

import warnings
# Suppress the PyTorch CUDA compatibility warning if it occurs
warnings.filterwarnings("ignore", message=".*is not compatible with the current PyTorch installation.*")

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from src.utils.config import config
from src.train import TrafficGRU

class TrafficPredictor:
    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        try:
            torch.zeros(1).to(self.device)
        except RuntimeError:
            self.device = torch.device('cpu')
        self.model_path = config.get('model_path', 'data/models/best_model.pth')
        self.model = self._load_model()
        
        # We need to maintain sequence history for predictions
        # For simplicity, we just use the current record and assume sequence length 1 
        # or pad with the current value to match seq_len = 12.
        # In a real system, we'd cache recent real-time data in Redis/Memcached.
        self.seq_len = 12
        
    def _load_model(self):
        # Must match training parameters
        input_size = 5
        hidden_size = 64
        num_layers = 2
        output_size = 1
        
        try:
            model = TrafficGRU(input_size, hidden_size, num_layers, output_size).to(self.device)
        except RuntimeError:
            self.device = torch.device('cpu')
            model = TrafficGRU(input_size, hidden_size, num_layers, output_size).to(self.device)
        
        if os.path.exists(self.model_path):
            model.load_state_dict(torch.load(self.model_path, map_location=self.device, weights_only=True))
            print(f"Model loaded from {self.model_path}")
        else:
            print(f"Warning: Model not found at {self.model_path}. Using untrained weights.")
            
        model.eval()
        return model

    def predict(self, df):
        """
        df: DataFrame from spark_etl containing features for the CURRENT timestamp.
        Returns: dict {segment_id: predicted_congestion_minutes}
        """
        if df is None or df.empty:
            return {}
            
        features = ['speed', 'hour', 'day_of_week', 'is_weekend', 'is_peak']
        
        # Simple sequence padding: copy current value seq_len times
        # Ideally, we should pull the last (seq_len-1) records from a cache
        
        predictions = {}
        with torch.no_grad():
            seg_ids = df['segment_id'].astype(int).values
            speeds = df['speed'].values / 100.0
            hours = df['hour'].values
            dows = df['day_of_week'].values
            weekends = df['is_weekend'].values
            peaks = df['is_peak'].values
            
            # Create feature matrix [N, 5]
            feats = np.column_stack([speeds, hours, dows, weekends, peaks])
            
            # Repeat to form sequence [N, seq_len, 5]
            seqs = np.repeat(feats[:, np.newaxis, :], self.seq_len, axis=1)
            x_tensor = torch.tensor(seqs, dtype=torch.float32).to(self.device)
            
            # Batch predict
            preds = self.model(x_tensor).cpu().numpy().flatten()
            
            for seg_id, pred in zip(seg_ids, preds):
                predictions[int(seg_id)] = max(0.0, float(pred))
                
        return predictions

# Singleton instance
predictor = TrafficPredictor()
