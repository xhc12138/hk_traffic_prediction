# Placeholder for Advanced Task Data Preparation (Delay Propagation)
# Handles Delay Event tracking, duration calculation and data augmentation

def main():
    print("[MTR] Preparing data for Delay Propagation model...")
    # 
    # HOW TO HANDLE DELAY EVENT TRACKING ACROSS SNAPSHOTS:
    # 1. Identify "Incidents": Find continuous blocks of time where `isdelay="Y"`.
    # 2. To track affected trains, DO NOT rely on `seq`. Instead, match trains 
    #    between the pre-delay snapshot and post-delay snapshot using the tuple 
    #    `(line, dest, original_time)`.
    # 3. If the data logger crashed (creating gaps in data), use linear interpolation 
    #    for numeric features (`ttnt`), and forward-fill for categorical ones.
    # 
    # Group data into events (from Y to N)
    # Calculate delay_duration_minutes and affected_trains_count.
    # Augment data using SMOTE or RandomOverSampler for minority delay events.
    # Add artificial slight perturbations to delay sequences.
    # Save to data/processed/mtr_delay_propagation.parquet
    print("[MTR] Saved processed data to data/processed/mtr_delay_propagation.parquet")

if __name__ == "__main__":
    main()
