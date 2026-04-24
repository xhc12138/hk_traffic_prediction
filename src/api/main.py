from fastapi import FastAPI, BackgroundTasks
import uvicorn
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
    
    if use_mock:
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
        raw_dir = os.path.join(project_root, config.get("mtr_raw_data_dir", "data/historical/mtr_nexttrain/raw"))
        json_files = glob.glob(os.path.join(raw_dir, "*.json"))
        
        if not json_files:
            print("[MTR] No raw data found. Please run data_logger.py first.")
            return
            
        latest_file = max(json_files, key=os.path.getctime)
        with open(latest_file, 'r', encoding='utf-8') as f:
            json_content = f.read()
            
        if spark_session is None:
            spark_session = create_spark_session()
            
        df = run_spark_etl_mtr(spark_session, json_content)
        
        if df.empty:
            print("[MTR] No valid data found in the latest JSON.")
            return

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