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

class MTRPropagationDataset(Dataset):
    def __init__(self, data):
        self.data = data
        self.features = ['up_ttnt_1', 'down_ttnt_1', 'hour', 'day_of_week', 'is_weekend', 'is_peak']
        
        self.data['up_ttnt_1'] = self.data['up_ttnt_1'] / 60.0
        self.data['down_ttnt_1'] = self.data['down_ttnt_1'] / 60.0
        
        self.X = self.data[self.features].values
        self.y_duration = self.data['delay_duration_minutes'].values
        self.y_affected = self.data['affected_trains_count'].values
        
    def __len__(self):
        return len(self.X)
        
    def __getitem__(self, idx):
        # Treat as sequence of length 1 for simplicity and robustness
        X = self.X[idx].reshape(1, -1)
        y = np.array([self.y_duration[idx], self.y_affected[idx]])
        return torch.tensor(X, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)

class MTRDelayPropagationModel(nn.Module):
    def __init__(self, input_size=6, hidden_size=64, num_layers=2):
        super().__init__()
        self.gru = nn.GRU(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 2) # Predict duration and affected count
        self.relu = nn.ReLU() # Outputs should be positive
        
    def forward(self, x):
        out, _ = self.gru(x)
        out = self.fc(out[:, -1, :])
        return self.relu(out)

def train_propagation_model():
    data_path = os.path.join(project_root, "data/processed/mtr_delay_propagation.parquet")
    model_path = os.path.join(project_root, "data/models/mtr_delay_propagation.pth")
    
    if not os.path.exists(data_path):
        print(f"[MTR] Data not found at {data_path}. High-level training skipped.")
        return
        
    print("[MTR] Loading data for Propagation Model...")
    df = pd.read_parquet(data_path)
    
    dataset = MTRPropagationDataset(df)
    if len(dataset) == 0:
        print("[MTR] Not enough data to train propagation model.")
        return
        
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
    
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False)
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    try:
        dummy = torch.zeros(1).to(device)
    except RuntimeError:
        device = torch.device('cpu')
        
    print(f"[MTR] Training on device: {device}")
    
    try:
        model = MTRDelayPropagationModel().to(device)
    except RuntimeError:
        print("[MTR] CUDA initialization failed. Falling back to CPU.")
        device = torch.device('cpu')
        model = MTRDelayPropagationModel().to(device)
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    epochs = 15
    best_loss = float('inf')
    
    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        
        pbar = tqdm(train_loader, desc=f"Epoch {epoch+1}/{epochs} [Train]")
        for X_batch, y_batch in pbar:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
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
                loss = criterion(outputs, y_batch)
                val_loss += loss.item()
                
        val_loss = val_loss / len(val_loader)
        print(f"[MTR] Epoch {epoch+1}/{epochs}, Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")
        
        if val_loss < best_loss:
            best_loss = val_loss
            os.makedirs(os.path.dirname(model_path), exist_ok=True)
            torch.save(model.state_dict(), model_path)
            print(f"[MTR] Saved best model to {model_path}")
            
    print("[MTR] Delay Propagation Model Training Complete!")

if __name__ == '__main__':
    import warnings
    warnings.filterwarnings("ignore")
    train_propagation_model()