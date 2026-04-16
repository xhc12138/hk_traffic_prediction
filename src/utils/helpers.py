import pandas as pd
from datetime import datetime

def extract_time_features(df, date_col='date', time_col='time'):
    """
    Extract time features from date and time columns.
    """
    # Combine date and time to a single datetime column if not already
    df['datetime'] = pd.to_datetime(df[date_col].astype(str) + ' ' + df[time_col].astype(str))
    
    # Extract features
    df['hour'] = df['datetime'].dt.hour
    df['day_of_week'] = df['datetime'].dt.dayofweek
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
    
    # Peak hours: 7-9 AM and 5-7 PM
    df['is_peak'] = ((df['hour'] >= 7) & (df['hour'] <= 9)) | ((df['hour'] >= 17) & (df['hour'] <= 19))
    df['is_peak'] = df['is_peak'].astype(int)
    
    return df

def calculate_congestion_label(speed):
    """
    Simple logic: congestion if speed < 30 km/h
    """
    return 1 if speed < 30 else 0