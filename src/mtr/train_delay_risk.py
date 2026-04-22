import os
import sys
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from pathlib import Path
from tqdm import tqdm

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from src.utils.config import config

class MTRRiskDataset(Dataset):
    def __init__(self, data, seq_len=10):
        self.data = data
        self.seq_len = seq_len
        self.features = ['up_ttnt_1', 'down_ttnt_1', 'hour', 'day_of_week', 'is_weekend', 'is_peak']
        
        self.data['up_ttnt_1'] = self.data['up_ttnt_1'] / 60.0
        self.data['down_ttnt_1'] = self.data['down_ttnt_1'] / 60.0
        
        self.segments = self.data[['line', 'sta']].drop_duplicates().values
        self.samples = []
        
        for line, sta in tqdm(self.segments, desc="Building sequences"):
            seg_data = self.data[(self.data['line'] == line) & (self.data['sta'] == sta)].sort_values('timestamp').reset_index(drop=True)
            if len(seg_data) <= self.seq_len:
                pad_size = self.seq_len + 1 - len(seg_data)
                padded_data = pd.concat([seg_data.iloc[[0]*pad_size]], ignore_index=True)
                seg_data = pd.concat([padded_data, seg_data], ignore_index=True)
                
            X_cols = seg_data[self.features].values
            y_col = seg_data['delay_risk_label'].values
            
            for i in range(len(seg_data) - self.seq_len):
                X_seq = X_cols[i:i+self.seq_len]
                y_val = y_col[i+self.seq_len - 1]
                self.samples.append((X_seq, y_val))
                
    def __len__(self):
        return len(self.samples)
        
    def __getitem__(self, idx):
        X, y = self.samples[idx]
        return torch.tensor(X, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)

class MTRDelayRiskGRU(nn.Module):
    def __init__(self, input_size=6, hidden_size=64, num_layers=2):
        super().__init__()
        self.gru = nn.GRU(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)
        self.sigmoid = nn.Sigmoid()
        
    def forward(self, x):
        out, _ = self.gru(x)
        out = self.fc(out[:, -1, :])
        return self.sigmoid(out)

def train_risk_model():
    data_path = os.path.join(project_root, "data/processed/mtr_delay_risk.parquet")
    model_path = os.path.join(project_root, "data/models/mtr_delay_risk.pth")
    
    if not os.path.exists(data_path):
        print(f"[MTR] Data not found at {data_path}. Run data_preparation_risk.py first.")
        return
        
    print("[MTR] Loading data for Risk Model...")
    df = pd.read_parquet(data_path)
    
    dataset = MTRRiskDataset(df, seq_len=10)
    if len(dataset) == 0:
        print("[MTR] Not enough data to train.")
        return
        
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
    
    train_loader = DataLoader(train_dataset, batch_size=256, shuffle=True, num_workers=2)
    val_loader = DataLoader(val_dataset, batch_size=256, shuffle=False, num_workers=2)
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    try:
        dummy = torch.zeros(1).to(device)
    except RuntimeError:
        print("[MTR] CUDA incompatible. Falling back to CPU.")
        device = torch.device('cpu')
        
    print(f"[MTR] Training on device: {device}")
    
    try:
        model = MTRDelayRiskGRU().to(device)
    except RuntimeError:
        print("[MTR] CUDA initialization failed. Falling back to CPU.")
        device = torch.device('cpu')
        model = MTRDelayRiskGRU().to(device)
    
    # Calculate pos weight for BCE with logits or just use BCELoss
    # Since delay events are rare, let's use weighted BCE if needed, but simple BCE is fine for now
    criterion = nn.BCELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    epochs = 5
    best_loss = float('inf')
    
    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        
        pbar = tqdm(train_loader, desc=f"Epoch {epoch+1}/{epochs} [Train]")
        for X_batch, y_batch in pbar:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs.squeeze(), y_batch)
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item()
            pbar.set_postfix({'loss': f"{loss.item():.4f}"})
            
        train_loss = running_loss / len(train_loader)
        
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                outputs = model(X_batch)
                loss = criterion(outputs.squeeze(), y_batch)
                val_loss += loss.item()
                
        val_loss = val_loss / len(val_loader)
        print(f"[MTR] Epoch {epoch+1}/{epochs}, Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")
        
        if val_loss < best_loss:
            best_loss = val_loss
            os.makedirs(os.path.dirname(model_path), exist_ok=True)
            torch.save(model.state_dict(), model_path)
            print(f"[MTR] Saved best model to {model_path}")
            
    print("[MTR] Delay Risk Model Training Complete!")

if __name__ == '__main__':
    import warnings
    warnings.filterwarnings("ignore")
    train_risk_model()