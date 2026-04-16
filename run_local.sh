#!/bin/bash
set -e

# Activate conda environment (assume hk_traffic is created)
source $(conda info --base)/etc/profile.d/conda.sh || true
conda activate hk_traffic || echo "Please activate hk_traffic environment manually"

export ENV=local

echo "================================================="
echo "Starting Traffic Prediction API & Spark Inference"
echo "Environment: $ENV"
echo "================================================="

python src/api/main.py