#!/bin/bash
set -e

# Activate conda environment
source $(conda info --base)/etc/profile.d/conda.sh || true
conda activate hk_traffic || echo "Please activate hk_traffic environment manually"

export ENV=local

echo "================================================="
echo "Starting ONLY MTR Data Logger"
echo "This will continuously fetch MTR schedule data"
echo "every 30 seconds to build the training dataset."
echo "Press CTRL+C to stop."
echo "================================================="

# Start the logger directly
python src/mtr/data_logger.py