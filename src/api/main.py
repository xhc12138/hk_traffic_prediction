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

# Global cache for latest predictions
latest_predictions: Dict[int, float] = {}
last_update_timestamp: str = ""
spark_session = None

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
    scheduler.start()
    
    # Run once immediately
    update_predictions()
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