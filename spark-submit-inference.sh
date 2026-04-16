#!/bin/bash
set -e

# Usage: bash spark-submit-inference.sh [local|cloud]

ENV=${1:-local}
export ENV=$ENV

# Basic extraction of master URL from yaml config (assuming simple format)
MASTER=$(grep 'master:' config/${ENV}.yaml | cut -d '"' -f 2)

echo "Submitting Spark Inference Job"
echo "Environment: $ENV"
echo "Master URL: $MASTER"

spark-submit \
    --master "$MASTER" \
    --conf spark.executor.memory=2g \
    --conf spark.driver.memory=2g \
    src/inference/spark_etl.py