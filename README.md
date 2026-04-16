# 香港主要幹道交通阻塞時間預測模組 (Congestion Duration Prediction Module)

這是一個基於 Spark 與 PyTorch 的實時交通擁堵預測後端服務，專為提供 Dashboard JSON 接口設計。

## 目錄結構
- `data/`：數據目錄（包含歷史和處理後的資料）。
- `src/`：原始碼。
- `config/`：本地與雲端配置切換。
- `run_local.sh`：本地一鍵啟動腳本。
- `spark-submit-inference.sh`：Spark 提交測試腳本。

## 快速開始 (Local 環境)

### 1. 準備數據
確保 `data/historical/irnAvgSpeed-all.xml` 已存在。

### 2. 數據清洗與特徵工程
```bash
conda activate hk_traffic
python src/data_preparation.py
```
此步驟會產生 `data/processed/train_data.parquet`。

### 3. 模型訓練 (PyTorch)
完全不使用 Spark，僅用 PyTorch (GPU 加速)。
```bash
python src/train.py
```
訓練好的模型會保存在 `data/models/best_model.pth`。

### 4. 啟動 FastAPI 與 Spark Inference
```bash
bash run_local.sh
```
此腳本會啟動後端服務，並使用 `APScheduler` 每 5 分鐘自動執行 Spark ETL 並更新預測結果。

## Dashboard 對接說明

接口提供兩個端點 (預設運行在 `http://127.0.0.1:8000`)：

### 1. 批量獲取所有預測
**GET** `/predictions`
```json
{
  "count": 250,
  "predictions": {
    "105500": 12.5,
    "105543": 0.0
  }
}
```
- **建議**：每 5 分鐘輪詢一次此接口，將預測結果顯示在全域地圖。

### 2. 單一路段查詢
**GET** `/predict?segment_id=105500`
```json
{
  "segment_id": 105500,
  "predicted_congestion_minutes": 12.5,
  "status": "Success"
}
```

## 雲端遷移
整個專案採用 config-driven。只需修改 `config/cloud.yaml` 中的 `master` URL 即可從本地切換到雲端 Spark 集群。
在部署時將 `ENV` 變數設為 `cloud`。