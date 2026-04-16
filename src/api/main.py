from fastapi import FastAPI, BackgroundTasks
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from typing import Dict, Optional
import sys
from pathlib import Path
import os
from contextlib import asynccontextmanager

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from src.utils.config import config
from src.inference.spark_etl import create_spark_session, fetch_realtime_xml, run_spark_etl
from src.inference.predictor import predictor

# Global cache for latest predictions
latest_predictions: Dict[int, float] = {}
spark_session = None

def update_predictions():
    global latest_predictions, spark_session
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
        print(f"Updated predictions for {len(preds)} segments.")
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
        "predictions": {k: round(v, 2) for k, v in latest_predictions.items()}
    }

if __name__ == "__main__":
    host = config.get('api_host', '0.0.0.0')
    port = config.get('api_port', 8000)
    uvicorn.run("src.api.main:app", host=host, port=port, reload=True)