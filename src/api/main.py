from fastapi import FastAPI, BackgroundTasks
import uvicorn
import math
import random
from apscheduler.schedulers.background import BackgroundScheduler
from typing import Dict, Optional
import sys
from pathlib import Path
import os
import time
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from src.utils.config import config
from src.inference.spark_etl import create_spark_session, fetch_realtime_xml, run_spark_etl
from src.inference.predictor import predictor

from src.mtr.inference.spark_etl_mtr import run_spark_etl_mtr
from src.mtr.inference.predictor_mtr import mtr_predictor
from src.bus.inference.spark_etl_bus import run_bus_etl

import glob

DEMO_MODE = os.getenv('DEMO_MODE', 'false').lower() == 'true'

# Global cache for latest predictions
latest_predictions: Dict[int, float] = {}
last_update_timestamp: str = ""
spark_session = None

# MTR Global cache
latest_mtr_risk: Dict[str, float] = {}
latest_mtr_propagation: Dict[str, dict] = {}
mtr_last_update_timestamp: str = ""

# BUS Global cache
latest_bus_data: Dict[str, list] = {}
bus_last_update_timestamp: str = ""

# Prefetch cache for specific routes to reduce latency for demonstration
prefetched_bus_eta: Dict[str, dict] = {}

def get_demo_stage():
    """
    Returns the current demo stage (1 or 2) and a seeded random number generator.
    The stage changes every 2 minutes (120 seconds).
    """
    time_window = int(time.time() / 120)
    # Seed the RNG with the time window so both Road and MTR updates get the same stage during this window
    rng = random.Random(time_window)
    stage = rng.choice([1, 2])
    return stage, rng

def load_latest_mtr_snapshot():
    """
    Load the latest real MTR snapshot if available.
    This is used by demo mode to preserve realistic UP/DOWN countdown values.
    """
    global spark_session
    raw_dir = os.path.join(project_root, config.get("mtr_raw_data_dir", "data/historical/mtr_nexttrain/raw"))
    json_files = glob.glob(os.path.join(raw_dir, "*.json"))
    if not json_files:
        return None

    latest_file = max(json_files, key=os.path.getctime)
    with open(latest_file, 'r', encoding='utf-8') as f:
        json_content = f.read()

    if spark_session is None:
        spark_session = create_spark_session()

    df = run_spark_etl_mtr(spark_session, json_content)
    if df.empty:
        return None
    return df

def update_bus_data():
    global latest_bus_data, bus_last_update_timestamp, spark_session
    print("[BUS] Running background task to update Bus data...")
    if spark_session is None:
        spark_session = create_spark_session()
        
    # We only process KMB periodically for UI demonstration to avoid 1.5GB GOV file OOM
    res = run_bus_etl(spark_session, task="kmb")
    if res and "kmb" in res:
        latest_bus_data["kmb"] = res["kmb"]
        bus_last_update_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[BUS] Background update complete. Cached {len(res['kmb'])} routes.")

def update_prefetched_bus_eta():
    """Periodically fetch ETA for demonstration routes to avoid frontend loading delay."""
    import requests
    routes_to_prefetch = ["1", "10"]
    for route in routes_to_prefetch:
        # Use data.etabus.gov.hk according to official spec
        # Ensure route doesn't have leading zeros and is uppercase
        clean_route = route.lstrip('0').upper() if route.isdigit() else route.upper()
        url = f"https://data.etabus.gov.hk/v1/transport/kmb/route-eta/{clean_route}/1"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                prefetched_bus_eta[route] = resp.json()
                print(f"[BUS] Prefetched ETA for route {route}")
            else:
                print(f"[BUS] Failed to prefetch ETA for route {route}: Status {resp.status_code}")
        except Exception as e:
            print(f"[BUS] Failed to prefetch ETA for route {route}: {e}")

def update_mtr_predictions():
    global latest_mtr_risk, latest_mtr_propagation, mtr_last_update_timestamp, spark_session
    use_mock = os.environ.get("MTR_USE_MOCK", "false").lower() == "true"
    
    import pandas as pd
    
    realtime_df = load_latest_mtr_snapshot()

    if DEMO_MODE:
        print("[MTR] Building DEMO MODE baseline from latest real snapshot when available...")
        if realtime_df is not None and not realtime_df.empty:
            df = realtime_df
        else:
            print("[MTR] Demo fallback: no real snapshot found, using synthetic baseline.")
            lines_stations = config.get("mtr_lines_stations", {})
            mock_data = []
            for line, stations in lines_stations.items():
                for sta in stations:
                    mock_data.append({
                        "line": line,
                        "sta": sta,
                        "up_ttnt_1": random.randint(1, 8),
                        "down_ttnt_1": random.randint(1, 8),
                        "hour": datetime.now().hour,
                        "day_of_week": datetime.now().weekday(),
                        "is_weekend": 1 if datetime.now().weekday() >= 5 else 0,
                        "is_peak": 0,
                    })
            if not mock_data:
                return
            df = pd.DataFrame(mock_data)
    elif use_mock:
        print("[MTR] Fetching MTR data and predicting in MOCK mode...")
        # Generate mock dataframe based on config
        lines_stations = config.get("mtr_lines_stations", {})
        mock_data = []
        for line, stations in lines_stations.items():
            for sta in stations:
                mock_data.append({"line": line, "sta": sta})
        
        if not mock_data:
            return
            
        df = pd.DataFrame(mock_data)
    else:
        print("[MTR] Fetching realtime MTR data in REAL mode...")
        if realtime_df is None:
            print("[MTR] No raw data found. Please run data_logger.py first.")
            return
        df = realtime_df

    if DEMO_MODE:
        stage, stage_rng = get_demo_stage()
        print(f"[MTR] Applying DEMO MODE transformations (Stage {stage})...")
        latest_mtr_risk = {}
        latest_mtr_propagation = {}

        for _, row in df.iterrows():
            key = f"{row['line']}-{row['sta']}"
            up_ttnt = round(float(row.get("up_ttnt_1", 0.0)), 1)
            down_ttnt = round(float(row.get("down_ttnt_1", 0.0)), 1)

            # Calm baseline for demo: most stations remain green.
            base_risk = 0.03 + (stage_rng.random() * 0.05)
            latest_mtr_risk[key] = {
                "delay_risk_probability": round(base_risk, 4),
                "up_ttnt": up_ttnt,
                "down_ttnt": down_ttnt,
            }
            latest_mtr_propagation[key] = {
                "delay_risk_probability": round(base_risk, 4),
                "delay_duration_minutes": 0.0,
                "affected_trains_count": 0,
                "color_code": "green",
                "up_ttnt": up_ttnt,
                "down_ttnt": down_ttnt,
            }

        num_delays = stage_rng.randint(1, 2) if stage == 1 else stage_rng.randint(3, 5)
        available_keys = list(latest_mtr_propagation.keys())

        if available_keys:
            delay_targets = stage_rng.sample(available_keys, min(num_delays, len(available_keys)))
            for idx, key in enumerate(delay_targets):
                is_severe = idx < max(1, num_delays // 2)
                delay_risk = 0.78 + (stage_rng.random() * 0.18) if is_severe else 0.38 + (stage_rng.random() * 0.18)
                color = "red" if is_severe else "yellow"
                duration = round(stage_rng.uniform(12, 22), 1) if is_severe else round(stage_rng.uniform(5, 12), 1)
                affected = stage_rng.randint(2, 5) if is_severe else stage_rng.randint(1, 2)

                latest_mtr_risk[key]["delay_risk_probability"] = round(delay_risk, 4)
                latest_mtr_propagation[key].update({
                    "delay_risk_probability": round(delay_risk, 4),
                    "delay_duration_minutes": duration,
                    "affected_trains_count": affected,
                    "color_code": color,
                })
                print(f"[MTR-DEMO] Stage {stage}: Injected {color} delay at {key}")
    else:
        # Primary Task
        latest_mtr_risk = mtr_predictor.predict_risk(df, mock=use_mock)
        # Advanced Task
        latest_mtr_propagation = mtr_predictor.predict_propagation(df, mock=use_mock)

    mtr_last_update_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[MTR] Updated predictions for {len(df)} stations at {mtr_last_update_timestamp}.")

def update_predictions():
    global latest_predictions, spark_session, last_update_timestamp
    print("Fetching realtime data...")
    xml_content = fetch_realtime_xml()
    if not xml_content:
        print("Failed to fetch data.")
        return
        
    if spark_session is None:
        spark_session = create_spark_session()
        
    print("Running Spark ETL...")
    df = run_spark_etl(spark_session, xml_content)
    
    if not df.empty:
        print("Running Predictor...")
        preds = predictor.predict(df)
        
        if DEMO_MODE:
            stage, _ = get_demo_stage()
            print(f"[ROAD] Applying DEMO MODE transformations (Stage {stage})...")
            # Create moving traffic waves based on time and segment_id
            t = time.time()
            for seg_id in preds.keys():
                # Generate a pseudo-random but temporally smooth congestion value
                # Using a combination of sine waves and segment_id to create moving "hotspots"
                try:
                    seg_num = int(seg_id)
                except:
                    seg_num = hash(seg_id)
                
                # Create 3 slow-moving waves
                wave1 = math.sin(seg_num / 1000.0 + t / 300.0)
                wave2 = math.cos(seg_num / 500.0 - t / 400.0)
                wave3 = math.sin(seg_num / 2000.0 + t / 200.0)
                
                # Combine waves and shift to 0-1 range
                combined = (wave1 + wave2 + wave3) / 3.0 # Range approx -1 to 1
                normalized = (combined + 1) / 2.0
                
                # Add some base noise
                noise = (hash(str(seg_id) + str(int(t/60))) % 100) / 100.0 * 0.2
                val = max(0.0, min(1.0, normalized + noise - 0.1))
                
                # Apply stage-specific distribution.
                # Note: frontend currently treats only `<= 0` as green, so we intentionally
                # generate exact 0.0 for the green bucket in demo mode.
                if stage == 1:
                    # Stage 1:
                    # - mostly green
                    # - some yellow
                    # - a small amount of orange/red
                    if val < 0.72:
                        delay = 0.0
                    elif val < 0.92:
                        delay = 1.0 + ((val - 0.72) / 0.20) * 4.0   # yellow: 1-5
                    elif val < 0.985:
                        delay = 6.0 + ((val - 0.92) / 0.065) * 12.0 # orange: 6-18
                    else:
                        delay = 21.0 + ((val - 0.985) / 0.015) * 9.0 # rare red: 21-30
                else:
                    # Stage 2:
                    # - a small amount of green
                    # - mostly yellow
                    # - a small amount of orange
                    # - almost no red
                    if val < 0.14:
                        delay = 0.0
                    elif val < 0.84:
                        delay = 1.0 + ((val - 0.14) / 0.70) * 4.0   # mostly yellow: 1-5
                    elif val < 0.98:
                        delay = 6.0 + ((val - 0.84) / 0.14) * 10.0  # some orange: 6-16
                    else:
                        delay = 18.0 + ((val - 0.98) / 0.02) * 2.0  # rare borderline orange/red
                
                # Clamp between 0 and 35
                preds[seg_id] = max(0, min(35, round(delay, 1)))

        latest_predictions = preds
        last_update_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Updated predictions for {len(preds)} segments at {last_update_timestamp}.")
    else:
        print("No valid data to predict.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler = BackgroundScheduler()
    interval = config.get('prediction_interval_minutes', 5)
    scheduler.add_job(update_predictions, 'interval', minutes=interval)
    scheduler.add_job(update_mtr_predictions, 'interval', seconds=15)
    # Bus data is relatively static, update every hour or just once
    scheduler.add_job(update_bus_data, 'interval', minutes=60)
    # Prefetch bus ETA every 30 seconds
    scheduler.add_job(update_prefetched_bus_eta, 'interval', seconds=30)
    scheduler.start()
    
    # Run once immediately
    update_predictions()
    update_mtr_predictions()
    update_bus_data()
    update_prefetched_bus_eta()
    yield
    
    # Shutdown
    scheduler.shutdown()
    if spark_session:
        spark_session.stop()

app = FastAPI(title="Traffic Prediction API", lifespan=lifespan)

@app.get("/")
def root():
    return {
        "message": "Traffic Prediction API is running",
        "endpoints": [
            "/predict?segment_id=XXXX",
            "/predictions"
        ],
        "status": "Success"
    }

@app.get("/predict")
def get_prediction(segment_id: int):
    pred = latest_predictions.get(segment_id)
    if pred is None:
        return {"segment_id": segment_id, "predicted_congestion_minutes": None, "status": "Not found or no data"}
    return {"segment_id": segment_id, "predicted_congestion_minutes": round(pred, 2), "status": "Success"}

@app.get("/predictions")
def get_all_predictions():
    return {
        "count": len(latest_predictions),
        "last_update": last_update_timestamp,
        "predictions": {k: round(v, 2) for k, v in latest_predictions.items()}
    }

# --- MTR Endpoints ---

@app.get("/mtr/predictions")
def get_mtr_risk_predictions(line: Optional[str] = None, sta: Optional[str] = None):
    """Primary Task: Delay Risk Probability"""
    if line and sta:
        key = f"{line}-{sta}"
        pred = latest_mtr_risk.get(key)
        if pred is None:
            return {"line": line, "sta": sta, "delay_risk_probability": None, "status": "Not found"}
        
        # pred could be a dict (with UP/DOWN) or a float
        if isinstance(pred, dict):
            res = {"line": line, "sta": sta, "status": "Success"}
            res.update(pred)
            return res
        else:
            return {"line": line, "sta": sta, "delay_risk_probability": pred, "status": "Success"}
        
    return {
        "count": len(latest_mtr_risk),
        "last_update": mtr_last_update_timestamp,
        "predictions": latest_mtr_risk
    }

@app.get("/mtr/delay-prediction")
def get_mtr_propagation_predictions(line: Optional[str] = None, sta: Optional[str] = None):
    """Advanced Task: Delay Duration + Affected Trains"""
    if line and sta:
        key = f"{line}-{sta}"
        pred = latest_mtr_propagation.get(key)
        if pred is None:
            return {"line": line, "sta": sta, "data": None, "status": "Not found"}
        
        result = {"line": line, "sta": sta}
        result.update(pred)
        result["status"] = "Success"
        return result
        
    return {
        "count": len(latest_mtr_propagation),
        "last_update": mtr_last_update_timestamp,
        "predictions": latest_mtr_propagation
    }

# --- BUS Endpoints ---

@app.get("/bus/routes")
def get_bus_routes(limit: int = 100):
    """Return aggregated KMB bus routes and stops (default limit to 100 to avoid huge JSONs)"""
    data = latest_bus_data.get("kmb", [])
    return {
        "count": len(data),
        "last_update": bus_last_update_timestamp,
        "routes": data[:limit] if limit > 0 else data
    }

@app.get("/bus/eta/{route}")
async def get_bus_eta(route: str):
    """Fetch real-time ETA for a specific KMB route. Uses cache for '1' and '10'."""
    # Serve from cache for demonstration routes
    if route in ["1", "10"] and route in prefetched_bus_eta:
        return prefetched_bus_eta[route]

    import aiohttp
    # Ensure route doesn't have leading zeros and is uppercase for KMB API
    clean_route = route.lstrip('0').upper() if route.isdigit() else route.upper()
    
    # The API endpoint: https://data.etabus.gov.hk/v1/transport/kmb/route-eta/{route}/{service_type}
    # Usually service_type is 1. We fetch service_type 1.
    url = f"https://data.etabus.gov.hk/v1/transport/kmb/route-eta/{clean_route}/1"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    return {"status": "Error", "message": f"KMB API returned {response.status}"}
    except Exception as e:
        return {"status": "Error", "message": str(e)}

@app.get("/map_config")
def get_map_config():
    return {
        "map_center": config.get("map_center", [22.3193, 114.1694]),
        "color_thresholds": config.get("color_thresholds", [0, 5, 20]),
        "prediction_api_endpoint": config.get("prediction_api_endpoint", "/predictions")
    }

@app.get("/road_network")
def get_road_network():
    geojson_path = os.path.join(project_root, config.get("road_network_geojson_path", "data/road_network/processed/road_network.geojson"))
    if os.path.exists(geojson_path):
        return FileResponse(geojson_path, media_type="application/geo+json")
    return JSONResponse(status_code=404, content={"message": "Road network GeoJSON not found."})

@app.get("/mtr_network")
def get_mtr_network():
    geojson_path = os.path.join(project_root, "data/road_network/processed/mtr_network.geojson")
    if os.path.exists(geojson_path):
        return FileResponse(geojson_path, media_type="application/geo+json")
    return JSONResponse(status_code=404, content={"message": "MTR network GeoJSON not found."})

# Mount frontend static files
frontend_dir = os.path.join(project_root, "frontend")
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

@app.get("/map")
def serve_map():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"message": "Map frontend not found."})

if __name__ == "__main__":
    host = config.get('api_host', '0.0.0.0')
    port = config.get('api_port', 8000)
    uvicorn.run("src.api.main:app", host=host, port=port, reload=True)
