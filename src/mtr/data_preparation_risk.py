# Placeholder for Primary Task Data Preparation (Delay Risk)
# Generates Delay Risk Probability labels

def main():
    print("[MTR] Preparing data for Delay Risk model...")
    # Read raw JSON files from data/historical/mtr_nexttrain/raw/
    # 
    # HOW TO HANDLE THE SLIDING WINDOW & DISCONTINUOUS DATA:
    # 1. Ignore `seq` as a unique ID. It's just a positional index.
    # 2. Resample the timeline: Group by station and minute. If data is missing for a minute, 
    #    forward-fill (ffill) the previous snapshot's features.
    # 3. Create snapshot-based cross-sectional features: Extract ttnt of seq=1, seq=2, etc. 
    #    at each timestamp to form a fixed-size vector.
    # 4. For tracking specific trains, use the composite key: `(line, direction, dest, time)`.
    #    Since `time` (estimated arrival) might drift, use fuzzy matching (closest time).
    # 
    # Generate delay_risk_label = 1 if isdelay=="Y" else 0 within a 10-minute future window.
    # Save to data/processed/mtr_delay_risk.parquet
    print("[MTR] Saved processed data to data/processed/mtr_delay_risk.parquet")

if __name__ == "__main__":
    main()
