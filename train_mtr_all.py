#!/usr/bin/env python
import os
import sys
import subprocess
from pathlib import Path

project_root = Path(__file__).resolve().parent

def run_script(script_path):
    print(f"\n{'='*60}")
    print(f"Running: {script_path}")
    print(f"{'='*60}\n")
    
    # We use subprocess to run the python script and pipe output to stdout
    result = subprocess.run([sys.executable, script_path], cwd=project_root)
    
    if result.returncode != 0:
        print(f"\n[ERROR] Script {script_path} exited with code {result.returncode}")
        return False
    return True

def main():
    print("="*60)
    print("MTR End-to-End Training Pipeline")
    print("="*60)
    
    # 1. Low-level task: Data Preparation
    if not run_script("src/mtr/data_preparation_risk.py"):
        sys.exit(1)
        
    # 2. Low-level task: Model Training
    if not run_script("src/mtr/train_delay_risk.py"):
        sys.exit(1)
        
    # 3. High-level task: Data Preparation
    print("\n[INFO] Starting High-Level Task (Propagation) Data Preparation...")
    result_prop_prep = subprocess.run([sys.executable, "src/mtr/data_preparation_propagation.py"], cwd=project_root)
    
    if result_prop_prep.returncode == 1:
        print("\n[INFO] No delay events found. Stopping high-level training pipeline as instructed.")
        print("[INFO] Low-level model is trained and ready. High-level model will use mock or skip until more data is collected.")
        sys.exit(0)
    elif result_prop_prep.returncode != 0:
        print(f"\n[ERROR] Script data_preparation_propagation.py exited with code {result_prop_prep.returncode}")
        sys.exit(1)
        
    # 4. High-level task: Model Training
    if not run_script("src/mtr/train_delay_propagation.py"):
        sys.exit(1)
        
    print("\n" + "="*60)
    print("MTR End-to-End Training Pipeline Completed Successfully!")
    print("Both Delay Risk and Delay Propagation models are ready for inference.")
    print("="*60)

if __name__ == "__main__":
    main()