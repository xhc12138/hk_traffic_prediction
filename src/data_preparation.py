import os
import glob
import pandas as pd
from lxml import etree
import sys
from pathlib import Path

# Add project root to sys.path so we can import src modules
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from src.utils.config import config
from src.utils.helpers import extract_time_features

def parse_xml_to_df(xml_file):
    """Parse a single XML file and return a pandas DataFrame."""
    try:
        tree = etree.parse(xml_file)
        root = tree.getroot()
        
        # Extract date and time
        date_elem = root.find('date')
        time_elem = root.find('time')
        
        if date_elem is None or time_elem is None:
            return pd.DataFrame()
            
        record_date = date_elem.text
        record_time = time_elem.text
        
        # Extract segments
        segments = root.find('segments')
        if segments is None:
            return pd.DataFrame()
            
        data = []
        for segment in segments.findall('segment'):
            seg_id = segment.find('segment_id')
            speed = segment.find('speed')
            valid = segment.find('valid')
            
            if seg_id is not None and speed is not None and valid is not None:
                # Only keep valid records
                if valid.text == 'Y':
                    data.append({
                        'date': record_date,
                        'time': record_time,
                        'segment_id': int(seg_id.text),
                        'speed': float(speed.text)
                    })
        
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Error parsing {xml_file}: {e}")
        return pd.DataFrame()

def calculate_congestion_minutes(df):
    """
    Calculate congestion duration:
    Speed < 30 km/h and duration >= 10 minutes cumulative.
    """
    # Sort by segment and time
    df = df.sort_values(by=['segment_id', 'datetime']).reset_index(drop=True)
    
    # Calculate time difference between consecutive records for the same segment
    df['time_diff'] = df.groupby('segment_id')['datetime'].diff().dt.total_seconds() / 60.0
    
    # Fill NaN with 0 (for the first record of each segment)
    # Or assume default 5 minutes interval
    df['time_diff'] = df['time_diff'].fillna(5.0)
    
    # Is congested at current time
    df['is_congested'] = (df['speed'] < 30).astype(int)
    
    # Calculate cumulative congestion duration
    # We create a group id that changes when is_congested is 0
    # So we can calculate cumulative sum within the congested periods
    df['congestion_block'] = (df['is_congested'] == 0).groupby(df['segment_id']).cumsum()
    
    # Calculate cumulative minutes for each congested block
    def cumsum_minutes(group):
        if group['is_congested'].iloc[0] == 1:
            return group['time_diff'].cumsum()
        else:
            return pd.Series([0] * len(group), index=group.index)
            
    df['congestion_minutes'] = df.groupby(['segment_id', 'congestion_block']).apply(cumsum_minutes).reset_index(level=[0, 1], drop=True)
    
    # For predicting future, we need the label. We can shift the congestion_minutes backward
    # to represent the future congestion minutes. 
    # Or simple label: speed
    # As per requirement: label is congestion_minutes
    df['label_congestion_minutes'] = df.groupby('segment_id')['congestion_minutes'].shift(-6) # Future 30 mins (assume 5 min intervals)
    
    # Fill NaN
    df['label_congestion_minutes'] = df['label_congestion_minutes'].fillna(0.0)
    
    return df

def main():
    historical_dir = config.get('historical_data_dir', 'data/historical')
    output_path = config.get('data_path', 'data/processed/train_data.parquet')
    
    # Find all xml files
    xml_files = glob.glob(os.path.join(historical_dir, '**', '*.xml'), recursive=True)
    
    if not xml_files:
        print(f"No XML files found in {historical_dir}")
        return
        
    print(f"Found {len(xml_files)} XML files. Parsing...")
    
    dfs = []
    for xml_file in xml_files:
        df = parse_xml_to_df(xml_file)
        if not df.empty:
            dfs.append(df)
            
    if not dfs:
        print("No valid data extracted.")
        return
        
    full_df = pd.concat(dfs, ignore_index=True)
    
    # Extract time features
    print("Extracting time features...")
    full_df = extract_time_features(full_df)
    
    # Calculate labels
    print("Calculating congestion labels...")
    full_df = calculate_congestion_minutes(full_df)
    
    # Drop intermediate cols if needed, or keep them
    # Ensure target directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Save to parquet
    print(f"Saving to {output_path}...")
    full_df.to_parquet(output_path, index=False)
    print("Data preparation complete!")

if __name__ == '__main__':
    main()