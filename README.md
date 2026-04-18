# 香港交通预测与港铁延误预警系统

这是一个基于 Spark 与 PyTorch 的实时交通拥堵与港铁延误预测后端服务，专为提供 Dashboard JSON 接口设计。

## 目录结构
- `data/`：数据目录（包含历史和处理后的资料）。
- `src/`：源码（分为 `inference/` 道路部分与 `mtr/` 港铁部分）。
- `config/`：本地与云端配置切换。
- `run_local.sh`：本地一键启动脚本（同时启动 API 与 MTR Logger）。
- `spark-submit-inference.sh`：Spark 提交测试脚本。

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

### 實時交通可視化交互地圖使用說明
我們現在提供了一個開箱即用的互動式地圖，直接將預測結果可視化在地圖上！

**訪問路徑：**
啟動服務後，直接在瀏覽器打開：`http://127.0.0.1:8000/map`

**功能特點：**
- **直觀顏色編碼**：綠色（暢通）、黃色（預計緩慢）、橙色（預計擁堵）、紅色（嚴重擁堵）。
- **實時更新**：地圖會每 30 秒自動向後端拉取最新的預測數據，並動態更新路段顏色。
- **互動詳情**：點擊任何高亮路段，即可在側邊欄看到該路段的具體街道名稱和預計擁堵時間。
- **配置驅動**：地圖的中心點、顏色閾值和數據來源都可以通過 `config/local.yaml` 和 `config/cloud.yaml` 輕鬆修改，無需更改前端代碼。

**與 Dashboard 組員對接方式：**
1. **Iframe 嵌入**：可以直接在 Dashboard 應用中使用 `<iframe src="http://<API_IP>:8000/map"></iframe>` 嵌入整個地圖。
2. **靜態資源遷移**：只需將 `frontend/` 資料夾複製到您的前端專案中，並修改 `map.js` 中的 API Endpoint 即可。

---

接口提供两个端点 (预设运行在 `http://127.0.0.1:8000`)：

### 1. 批量获取所有路网预测
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

### 2. MTR 延误概率预测 (初级任务)
**GET** `/mtr/predictions`
```json
{
  "count": 100,
  "predictions": {
    "TCL-OLY": 0.23
  }
}
```

### 3. MTR 延误事件高级预测 (高级任务)
**GET** `/mtr/delay-prediction?line=TCL&sta=OLY`
```json
{
  "line": "TCL",
  "sta": "OLY",
  "delay_risk_probability": 0.85,
  "delay_duration_minutes": 14.8,
  "affected_trains_count": 3,
  "color_code": "red",
  "status": "Success"
}
```

## 雲端遷移
整個專案採用 config-driven。只需修改 `config/cloud.yaml` 中的 `master` URL 即可從本地切換到雲端 Spark 集群。
在部署時將 `ENV` 變數設為 `cloud`。