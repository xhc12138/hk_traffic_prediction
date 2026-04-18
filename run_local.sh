#!/bin/bash
set -e

# Activate conda environment (assume hk_traffic is created)
source $(conda info --base)/etc/profile.d/conda.sh || true
conda activate hk_traffic || echo "Please activate hk_traffic environment manually"

export ENV=local
export MTR_USE_MOCK=true

# Parse arguments for mock mode
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --real) export MTR_USE_MOCK=false ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

echo "================================================="
echo "Starting Traffic Prediction API"
echo "Environment: $ENV"
echo "MTR Mock Mode: $MTR_USE_MOCK"
echo "================================================="

# Start the server
echo "Starting FastAPI server..."
echo "You can view the interactive map at: http://127.0.0.1:8000/map"

# Open the browser if running on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    sleep 2 && open "http://127.0.0.1:8000/map" &
fi

# Start API
python src/api/main.py