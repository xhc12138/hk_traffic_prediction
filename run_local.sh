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

# Start the server
echo "Starting FastAPI server..."
echo "You can view the interactive map at: http://127.0.0.1:8000/map"

# Open the browser if running on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    sleep 2 && open "http://127.0.0.1:8000/map" &
fi

python src/api/main.py