# 港铁延误预测功能详解 (MTR Delay Prediction)

## 1. 核心目标
作为**香港主要干道交通阻塞时间预测模块**的延伸，本子模块 (`src/mtr/`) 专注于利用香港政府开放数据平台提供的 MTR Next Train API，实时抓取、清洗并预测港铁 10 条主要线路、100 多个车站的列车延误情况。

与道路交通预测不同，MTR 模块的数据具有“快照”和“滑动窗口”的特性，且缺乏每辆列车的全局唯一 ID。因此，我们将其分解为两个难度递进的独立任务：
- **初级任务 (Delay Risk Probability)**：预测某线路某车站未来 10 分钟内发生延误 (`isdelay="Y"`) 的概率（二分类）。
- **高级任务 (Delay Duration & Affected Trains)**：当检测到延误事件发生时，预测该事件的持续时间（分钟）和受影响的列车数量（系统级理解）。

## 2. 数据流与采集 (`src/mtr/data_logger.py`)

### 2.1 API 数据源
- **接口**：`https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php?line={line}&sta={sta}`
- **频率**：通过 `asyncio` 和 `aiohttp` 每 30 秒轮询一次所有合法站点。
- **存储**：原始 JSON 保存在 `data/historical/mtr_nexttrain/raw/` 目录下。

### 2.2 数据处理挑战
1. **API 速率限制**：轮询时加入 `asyncio.sleep(0.5)` 防止 HTTP 429 错误。
2. **缺乏唯一 ID**：每个 JSON 文件只是当前时刻的快照。我们提取各方向 (UP/DOWN) 第一班列车的预计到站时间 (`ttnt`) 作为该时刻的基准特征。

## 3. 初级任务：延误概率预测 (Delay Risk)

### 3.1 数据准备 (`src/mtr/data_preparation_risk.py`)
- **特征工程**：提取 `up_ttnt_1` 和 `down_ttnt_1`，结合时间特征（小时、星期几、是否周末、是否高峰）。
- **标签生成**：通过反向滚动窗口 (Rolling Window Backward) 计算未来 10 步（约 5 分钟）内的 `isdelay` 最大值。只要未来有 1 帧为 `"Y"`，则当前帧标签为 `1`，否则为 `0`。

### 3.2 模型训练 (`src/mtr/train_delay_risk.py`)
- **网络结构**：单向 GRU (`MTRDelayRiskGRU`)，使用 `nn.Sigmoid()` 输出 0~1 的概率。
- **损失函数**：**BCELoss** (Binary Cross Entropy)。

## 4. 高级任务：延误传播预测 (Delay Propagation)

### 4.1 事件驱动的数据准备 (`src/mtr/data_preparation_propagation.py`)
该任务**仅在发生延误事件时触发**。
- **事件聚合**：扫描整个时间线，寻找连续的 `isdelay="Y"` 时间块，将其聚合成独立的“延误事件”。
- **标签提取**：
  - `delay_duration_minutes`: 延误事件结束时间减去开始时间。
  - `affected_trains_count`: 估算受影响的班次。
- **数据增强 (Data Augmentation)**：由于重大延误事件是“稀有事件”（Rare Events），代码采用**高斯噪声扰动 (Gaussian Noise)** 结合复制策略，对少数延误样本进行 5 倍的数据增强。若全量数据中未发现任何延误事件，脚本会抛出退出码中止后续高级任务的训练。

### 4.2 模型训练 (`src/mtr/train_delay_propagation.py`)
- **网络结构**：多输出 GRU (`MTRDelayPropagationModel`)，使用 `nn.ReLU()` 确保预测的持续时间和受影响车辆数为非负值。
- **损失函数**：**MSELoss** (Mean Squared Error)。

## 5. 实时推理管道 (Inference Pipeline)

### 5.1 Spark ETL (`src/mtr/inference/spark_etl_mtr.py`)
- MTR 推理同样遵循大数据架构，利用 Spark RDD 处理实时拉取的 JSON 字符串。
- 将 `UP` 和 `DOWN` 数组扁平化，提取 `ttnt` 特征，并补充时间上下文。

### 5.2 联合预测器 (`src/mtr/inference/predictor_mtr.py`)
- `MTRPredictor` 作为一个单例对象，在初始化时同时加载初级 (`mtr_delay_risk.pth`) 和高级 (`mtr_delay_propagation.pth`) 两个 PyTorch 模型。
- **降级容错机制**：内置 CUDA 检测，若硬件不支持（如 RTX 5000 系列的 `sm_120`），会自动优雅降级至 CPU 模式。

### 5.3 MOCK 模式设计
- 考虑到数据采集和模型训练需要漫长的等待时间，系统内置了 **MOCK 模式**。
- 启动服务时，可通过 `MTR_USE_MOCK=true` 环境变量生成合理的假数据。
- 在 `run_local.sh` 中，使用 `--real` 参数可关闭 MOCK 模式，加载真实的 PyTorch 模型进行推理。

## 6. 前端 Web 渲染与交互设计 (Map Dashboard)

MTR 的延误预测不仅提供了 REST API，还与系统内置的 **Leaflet.js** 地图 Dashboard 深度整合，提供了专业级的系统调度监控体验。

### 6.1 MTR GeoJSON 网络构建
为了在地图上精确渲染地铁线路，我们在 `data/road_network/processed/mtr_network.geojson` 中构建了专用的空间数据。
- 数据来源于开源社区（如 `mtr-map-master`），通过 Python 脚本将原有的 SVG 像素坐标进行了**仿射变换 (Affine Transformation)**，精确映射到香港真实的经纬度 (EPSG:4326) 上。
- 每一条线路（如荃湾线、东涌线）都被赋予了港铁官方的主题色（如 `#E2231A`, `#F8912E`），以 `LineString` 的形式渲染在地图顶层。

### 6.2 实时双系统切换与交互 (UI/UX)
- **双系统切换**：在地图右上角设有 `Road Traffic System` 与 `MTR Delay System` 切换按钮。点击后，不仅地图图层会平滑替换，左侧边栏 (Sidebar) 也会同步切换到 MTR 专属的面板结构。
- **站点悬停与点击 (Tooltip & Details)**：
  - 鼠标悬停 (Hover) 站点时，弹出气泡会实时显示两个方向的**下一班列车等候时间 (ttnt)** 和延误风险概率。
  - 点击 (Click) 站点时，侧边栏会详细展示该站的高级预测评估：预计恢复时长 (Duration) 与受影响列车数 (Affected Trains)。
- **延误事件大屏监控 (Active Delay Events)**：
  - 左侧边栏底部有一个**全局事件统计列表**。当任何站点的风险阈值触发“红黄警报”时，该面板会自动生成闪烁的警告条目，显示受影响范围。
  - 调度员只需点击列表中的警报事件，地图便会自动**平移并放大 (Zoom)** 到事故发生的地铁站，实现极速的指挥响应。

## 7. API 暴露与定时任务 (`src/api/main.py`)
在原有的 FastAPI 服务上新增了两个路由：
1. **`GET /mtr/predictions`**：批量返回所有站点的初级延误概率。
2. **`GET /mtr/delay-prediction`**：返回高级任务预测（包含概率、预计持续时间、受影响车辆数、实时等候时间 `ttnt` 以及相应的警报颜色代码）。
3. **`GET /mtr_network`**：向前端提供 MTR GeoJSON 渲染数据。
- **APScheduler** 每 15 秒在后台刷新一次 MTR 的预测缓存，供前端 Dashboard 高频轮询。