import os
import sys
import glob
import json
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from src.utils.config import config

def load_raw_data(raw_dir):
    files = sorted(glob.glob(os.path.join(raw_dir, "*.json")))
    if not files:
        return pd.DataFrame()
        
    print(f"[MTR] Found {len(files)} raw JSON files.")
    
    data_rows = []
    for f in tqdm(files, desc="Parsing JSON files"):
        with open(f, 'r') as fp:
            try:
                d = json.load(fp)
            except json.JSONDecodeError:
                continue
                
            ts = d.get('collected_at')
            if not ts:
                continue
                
            try:
                dt = pd.to_datetime(ts, format="%Y%m%d_%H%M%S")
            except:
                continue
                
            for line, stas in d.get('data', {}).items():
                for sta, info in stas.items():
                    isdelay = info.get('isdelay', 'N')
                    
                    up_ttnt_1, down_ttnt_1 = 0.0, 0.0
                    
                    try:
                        up_list = info.get('data', {}).get(f"{line}-{sta}", {}).get('UP', [])
                        if up_list:
                            up_ttnt_1 = float(up_list[0].get('ttnt', 0))
                    except:
                        pass
                        
                    try:
                        down_list = info.get('data', {}).get(f"{line}-{sta}", {}).get('DOWN', [])
                        if down_list:
                            down_ttnt_1 = float(down_list[0].get('ttnt', 0))
                    except:
                        pass
                        
                    data_rows.append({
                        'timestamp': dt,
                        'line': line,
                        'sta': sta,
                        'isdelay': 1 if isdelay == 'Y' else 0,
                        'up_ttnt_1': up_ttnt_1,
                        'down_ttnt_1': down_ttnt_1
                    })
                    
    return pd.DataFrame(data_rows)

def prepare_risk_data():
    raw_dir = os.path.join(project_root, config.get("mtr_raw_data_dir", "data/historical/mtr_nexttrain/raw"))
    output_path = os.path.join(project_root, "data/processed/mtr_delay_risk.parquet")
    
    df = load_raw_data(raw_dir)
    if df.empty:
        print("[MTR] No raw data found.")
        sys.exit(0)
        
    print("[MTR] Extracting features and labels...")
    df = df.sort_values(by=['line', 'sta', 'timestamp']).reset_index(drop=True)
    
    # Fill missing values
    df['up_ttnt_1'] = df.groupby(['line', 'sta'])['up_ttnt_1'].ffill().fillna(0)
    df['down_ttnt_1'] = df.groupby(['line', 'sta'])['down_ttnt_1'].ffill().fillna(0)
    
    # Time features
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
    df['is_peak'] = ((df['hour'] >= 7) & (df['hour'] <= 9)) | ((df['hour'] >= 17) & (df['hour'] <= 19))
    df['is_peak'] = df['is_peak'].astype(int)
    
    # Delay risk label: 1 if isdelay == 1 in the next 10 minutes (approx 20 steps if 30s interval)
    # Using rolling max over next 20 rows per station
    # First reverse the dataframe to use rolling backward
    df_rev = df.iloc[::-1].copy()
    
    df_rev['delay_risk_label'] = df_rev.groupby(['line', 'sta'])['isdelay'].transform(lambda x: x.rolling(window=10, min_periods=1).max())
    
    # Re-reverse
    df['delay_risk_label'] = df_rev['delay_risk_label'].iloc[::-1].values
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_parquet(output_path, index=False)
    print(f"[MTR] Saved processed data to {output_path}")
    print(f"[MTR] Total rows: {len(df)}, Delay positive samples: {df['delay_risk_label'].sum()}")

if __name__ == "__main__":
    prepare_risk_data()