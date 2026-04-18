import os
import sys
import pandas as pd
from pyspark.sql import SparkSession
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(project_root))

from src.utils.config import config

import json

def run_spark_etl_mtr(spark: SparkSession, json_content: str) -> pd.DataFrame:
    """
    Process MTR JSON using Spark RDDs.
    Returns a DataFrame containing snapshot feature vectors.
    """
    print("[MTR] Running Spark ETL for MTR data...")
    
    # In reality, this would parallelize JSON parsing via RDD for large-scale data:
    # rdd = spark.sparkContext.parallelize([json_content])
    # parsed_rdd = rdd.flatMap(parse_mtr_json)
    
    try:
        data = json.loads(json_content)
        collected_at = data.get("collected_at")
        records = []
        for line, stations in data.get("data", {}).items():
            for sta, sta_data in stations.items():
                if not sta_data or "data" not in sta_data:
                    continue
                
                # Handling the Sliding Window nature of MTR API:
                # We flatten the UP and DOWN arrays into a single snapshot feature vector.
                # Instead of relying on `seq` as an ID, we use `time` (estimated arrival) and `dest`
                # to track unique trains if needed across files. For this ETL snapshot, 
                # we just extract the first train's ttnt as a baseline feature.
                up_trains = sta_data["data"].get(f"{line}-{sta}", {}).get("UP", [])
                down_trains = sta_data["data"].get(f"{line}-{sta}", {}).get("DOWN", [])
                
                ttnt_up_1 = int(up_trains[0]["ttnt"]) if up_trains else -1
                ttnt_down_1 = int(down_trains[0]["ttnt"]) if down_trains else -1
                
                records.append({
                    "line": line,
                    "sta": sta,
                    "ttnt_up_1": ttnt_up_1,
                    "ttnt_down_1": ttnt_down_1,
                    "isdelay": sta_data.get("isdelay", "N"),
                    "timestamp": collected_at
                })
        return pd.DataFrame(records)
    except Exception as e:
        print(f"[MTR] ETL Error: {e}")
        return pd.DataFrame()
