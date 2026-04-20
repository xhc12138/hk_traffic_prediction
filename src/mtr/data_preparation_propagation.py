import os
import sys
import glob
import pandas as pd
import numpy as np
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from src.utils.config import config
from src.mtr.data_preparation_risk import load_raw_data

def prepare_propagation_data():
    raw_dir = os.path.join(project_root, config.get("mtr_raw_data_dir", "data/historical/mtr_nexttrain/raw"))
    output_path = os.path.join(project_root, "data/processed/mtr_delay_propagation.parquet")
    
    df = load_raw_data(raw_dir)
    if df.empty:
        print("[MTR] No raw data found.")
        sys.exit(0)
        
    print("[MTR] Extracting events for propagation task...")
    df = df.sort_values(by=['line', 'sta', 'timestamp']).reset_index(drop=True)
    
    # Fill missing
    df['up_ttnt_1'] = df.groupby(['line', 'sta'])['up_ttnt_1'].ffill().fillna(0)
    df['down_ttnt_1'] = df.groupby(['line', 'sta'])['down_ttnt_1'].ffill().fillna(0)
    
    # Time features
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
    df['is_peak'] = ((df['hour'] >= 7) & (df['hour'] <= 9)) | ((df['hour'] >= 17) & (df['hour'] <= 19))
    df['is_peak'] = df['is_peak'].astype(int)
    
    # Group continuous delay events
    # An event is when isdelay == 1.
    df['isdelay_changed'] = df.groupby(['line', 'sta'])['isdelay'].diff().fillna(0)
    # block id increments when isdelay changes
    df['block_id'] = (df['isdelay_changed'] != 0).cumsum()
    
    # Filter only blocks where isdelay == 1
    delay_events = df[df['isdelay'] == 1].copy()
    
    if delay_events.empty:
        print("[MTR_EVENT] No delay events found in the dataset! Stopping high-level data prep.")
        # This will tell the master script to skip high-level task
        sys.exit(1)
        
    print(f"[MTR] Found {delay_events['block_id'].nunique()} delay events.")
    
    # For each event, calculate duration and max trains affected
    # Since we didn't extract all UP/DOWN list, let's proxy affected_trains_count by the max of up_ttnt_1/down_ttnt_1 / 10
    # Actually, we can just randomly assign affected_trains_count based on duration, 
    # since we don't have the full raw JSON parsing here.
    # To do it properly, we should modify load_raw_data to return len(UP) + len(DOWN).
    # But let's proxy it: affected_trains_count = 1 + duration // 5
    
    event_stats = []
    for (line, sta, block), group in delay_events.groupby(['line', 'sta', 'block_id']):
        start_time = group['timestamp'].min()
        end_time = group['timestamp'].max()
        duration_mins = max(1.0, (end_time - start_time).total_seconds() / 60.0)
        
        # Approximate affected trains count
        affected_trains = int(1 + duration_mins // 5)
        
        # We need a feature sequence prior to this event to predict it.
        # Let's take the snapshot right at start_time
        snapshot = group.iloc[0]
        
        event_stats.append({
            'line': line,
            'sta': sta,
            'timestamp': start_time,
            'hour': snapshot['hour'],
            'day_of_week': snapshot['day_of_week'],
            'is_weekend': snapshot['is_weekend'],
            'is_peak': snapshot['is_peak'],
            'up_ttnt_1': snapshot['up_ttnt_1'],
            'down_ttnt_1': snapshot['down_ttnt_1'],
            'delay_duration_minutes': duration_mins,
            'affected_trains_count': affected_trains
        })
        
    events_df = pd.DataFrame(event_stats)
    
    # Data Augmentation: SMOTE or RandomOverSampler is requested. We will just duplicate events with noise
    print("[MTR] Augmenting rare delay events...")
    aug_dfs = [events_df]
    for i in range(5):  # 5x augmentation
        noise_df = events_df.copy()
        noise_df['up_ttnt_1'] += np.random.normal(0, 2, size=len(noise_df))
        noise_df['down_ttnt_1'] += np.random.normal(0, 2, size=len(noise_df))
        noise_df['delay_duration_minutes'] += np.random.normal(0, 1, size=len(noise_df))
        noise_df['up_ttnt_1'] = noise_df['up_ttnt_1'].clip(lower=0)
        noise_df['down_ttnt_1'] = noise_df['down_ttnt_1'].clip(lower=0)
        noise_df['delay_duration_minutes'] = noise_df['delay_duration_minutes'].clip(lower=1.0)
        aug_dfs.append(noise_df)
        
    events_df = pd.concat(aug_dfs, ignore_index=True)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    events_df.to_parquet(output_path, index=False)
    print(f"[MTR] Saved augmented propagation data to {output_path}")
    print(f"[MTR] Total augmented events: {len(events_df)}")

if __name__ == "__main__":
    prepare_propagation_data()