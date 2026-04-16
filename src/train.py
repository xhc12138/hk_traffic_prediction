import os
import sys
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from pathlib import Path


import warnings
# Suppress the PyTorch CUDA compatibility warning if it occurs
warnings.filterwarnings("ignore", message=".*is not compatible with the current PyTorch installation.*")

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from src.utils.config import config

class TrafficDataset(Dataset):
    def __init__(self, data, seq_len=12):
        self.data = data
        self.seq_len = seq_len
        self.features = ['speed', 'hour', 'day_of_week', 'is_weekend', 'is_peak']
        
        # Normalize features
        self.data['speed'] = self.data['speed'] / 100.0  # simple scaling
        
        self.segments = self.data['segment_id'].unique()
        self.samples = []
        
        # Build sequence samples per segment
        for seg in self.segments:
            seg_data = self.data[self.data['segment_id'] == seg].sort_values('datetime').reset_index(drop=True)
            if len(seg_data) <= self.seq_len:
                # Pad to seq_len + 1 to have at least one sample
                pad_size = self.seq_len + 1 - len(seg_data)
                padded_data = pd.concat([seg_data.iloc[[0]*pad_size]], ignore_index=True)
                seg_data = pd.concat([padded_data, seg_data], ignore_index=True)
                
            X_cols = seg_data[self.features].values
            y_col = seg_data['label_congestion_minutes'].values
            
            for i in range(len(seg_data) - self.seq_len):
                X_seq = X_cols[i:i+self.seq_len]
                y_val = y_col[i+self.seq_len - 1] # label of the last timestamp
                self.samples.append((X_seq, y_val))
                
    def __len__(self):
        return len(self.samples)
        
    def __getitem__(self, idx):
        X, y = self.samples[idx]
        return torch.tensor(X, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)

class TrafficGRU(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers, output_size):
        super(TrafficGRU, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        self.gru = nn.GRU(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, output_size)
        
    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        out, _ = self.gru(x, h0)
        # Decode the hidden state of the last time step
        out = self.fc(out[:, -1, :])
        return out

def train_model():
    data_path = config.get('data_path', 'data/processed/train_data.parquet')
    model_path = config.get('model_path', 'data/models/best_model.pth')
    
    if not os.path.exists(data_path):
        print(f"Data not found at {data_path}. Please run data_preparation.py first.")
        return
        
    print("Loading data...")
    df = pd.read_parquet(data_path)
    
    print("Creating dataset...")
    dataset = TrafficDataset(df, seq_len=12) # e.g. 60 mins / 5 mins = 12
    if len(dataset) == 0:
        print("Not enough data to train.")
        return
        
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
    
    train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=64, shuffle=False)
    
    # Model parameters
    input_size = 5 # speed, hour, day_of_week, is_weekend, is_peak
    hidden_size = 64
    num_layers = 2
    output_size = 1
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    # Check if GPU is compatible, otherwise fallback
    try:
        dummy = torch.zeros(1).to(device)
    except RuntimeError:
        print("CUDA device incompatible. Falling back to CPU.")
        device = torch.device('cpu')
    print(f"Training on device: {device}")
    
    try:
        model = TrafficGRU(input_size, hidden_size, num_layers, output_size).to(device)
    except RuntimeError:
        print("CUDA initialization failed (possibly due to incompatible architecture like RTX 5000 series). Falling back to CPU.")
        device = torch.device('cpu')
        model = TrafficGRU(input_size, hidden_size, num_layers, output_size).to(device)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    epochs = 10
    best_loss = float('inf')
    
    train_losses = []
    val_losses = []
    
    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs.squeeze(), y_batch)
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item()
            
        train_loss = running_loss / len(train_loader)
        train_losses.append(train_loss)
        
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                outputs = model(X_batch)
                loss = criterion(outputs.squeeze(), y_batch)
                val_loss += loss.item()
                
        val_loss = val_loss / len(val_loader)
        val_losses.append(val_loss)
        
        print(f"Epoch {epoch+1}/{epochs}, Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")
        
        if val_loss < best_loss:
            best_loss = val_loss
            os.makedirs(os.path.dirname(model_path), exist_ok=True)
            torch.save(model.state_dict(), model_path)
            print(f"Saved best model to {model_path}")
            
    print("Training complete!")

if __name__ == '__main__':
    train_model()