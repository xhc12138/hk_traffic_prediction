# 项目文件架构与各文件作用详解

本指南详细梳理了香港交通预测与港铁延误预警系统 (`hk_traffic_prediction`) 的目录结构及每一个文件的核心职责。

---

## 根目录文件
- **`README.md`**: 全项目综合部署、测试与接口调用指南（供团队协作与 Dashboard 对接）。
- **`requirements.txt`**: Python 依赖包清单（如 `torch`, `pyspark`, `fastapi`, `aiohttp` 等）。
- **`run_local.sh`**: 本地一键启动脚本，包含激活环境、启动后台 API 服务及通过 `--real` 参数控制 MTR Mock 模式。
- **`spark-submit-inference.sh`**: Spark 提交测试脚本，用于向独立的 Spark Master 节点提交道路和 MTR 的 ETL 任务。
- **`train_mtr_all.py`**: MTR 延误预测全流程自动化训练脚本。串联执行初级和高级的数据准备、模型训练。
- **`test_api.py`**: 后端 API 接口自动化测试脚本，用于验证所有的路由状态及响应时间。
- **`Dockerfile`**: 云端容器化部署文件，包含 Java 17、PyTorch 环境及项目代码。
- **`road_traffic_prediction.md`**: 道路交通预测功能（Road Traffic Prediction）的系统级实现详解。
- **`mtr_delay_prediction.md`**: 港铁延误预测功能（MTR Delay Prediction）的系统级实现详解。
- **`project_structure.md`**: （当前文档）项目文件架构解析。
- **`cloud_migration_guide.md`**: 生产环境云端迁移与 Spark RDD 集群配置指导。

---

## 目录：`data/`
存储所有的原始数据、清洗后的 Parquet 文件及模型权重。**该目录未被纳入 Git 版本控制。**
- **`historical/`**:
  - `processed/`: 手动下载的历史道路交通 XML 文件。
  - `mtr_nexttrain/raw/`: 由 `data_logger.py` 自动抓取生成的 MTR Next Train JSON 文件集合。
- **`processed/`**:
  - `train_data.parquet`: 道路交通清洗后数据。
  - `mtr_delay_risk.parquet`: MTR 初级任务（概率预测）清洗后数据。
  - `mtr_delay_propagation.parquet`: MTR 高级任务（延误传播）事件聚合后数据。
- **`models/`**:
  - `best_model.pth`: 道路交通 GRU 模型权重。
  - `mtr_delay_risk.pth`: MTR 初级二分类模型权重。
  - `mtr_delay_propagation.pth`: MTR 高级回归模型权重。
- **`road_network/`**: 用于前端渲染的 GeoJSON 地图文件。
  - `processed/road_network.geojson`: 道路交通骨架。
  - `processed/mtr_network.geojson`: 港铁线路与站点的真实坐标网络图。

---

## 目录：`mtr-map-master/`
社区开源的港铁网络静态资源。
- **`stations.csv` / `paths.csv`**: 包含 SVG 像素坐标系的港铁线路与车站数据。已被项目根目录的 `process_mtr_csv.py` 读取、仿射变换为真实的经纬度坐标，并生成 `mtr_network.geojson` 供前端 Leaflet 渲染使用。

---

## 目录：`config/`
集中管理项目配置，实现 Local / Cloud 零代码切换。
- **`local.yaml`**: 本地环境配置，如 `master: "local[*]"`，各类文件的本地相对路径，以及 MTR 站点的列表字典。
- **`cloud.yaml`**: 云端环境配置，包含真实的 Spark 集群 Master URL 和部署所需的环境变量。

---

## 目录：`frontend/`
前端 Dashboard 原型文件。
- **`index.html`**: Web UI 的入口。
- **`map.js`**: 地图渲染与 API 轮询逻辑，负责定时调用后端的 `/predictions` 及 `/mtr/delay-prediction`。
- **`styles.css`**: 界面样式。

---

## 目录：`src/`
所有核心 Python 源代码存放处。按业务功能划分为全局、道路交通、MTR 和 API 四大模块。

### 1. 全局工具 (`src/utils/`)
- **`config.py`**: 环境变量解析器，根据系统 `ENV` 自动加载对应的 `.yaml` 配置文件。
- **`helpers.py`**: 通用的特征工程工具函数，负责从时间戳中提取 `hour`, `day_of_week`, `is_weekend`, `is_peak` 等周期性特征。

### 2. 道路交通模块 (Road Traffic)
- **`data_preparation.py`**: 离线处理历史 XML 数据，计算车速特征，生成拥堵分钟数标签，保存为 Parquet。
- **`train.py`**: 使用 PyTorch 构建 GRU 神经网络，对道路拥堵时长进行回归训练。
- **`inference/`**:
  - `spark_etl.py`: 负责实时拉取运输署 XML，通过 PySpark RDD `flatMap` 解析为 Pandas DataFrame。
  - `predictor.py`: 加载 `best_model.pth`，接收 Spark ETL 特征并批量输出道路预测字典。

### 3. 港铁延误模块 (`src/mtr/`)
独立于道路模块，专为 MTR JSON 快照与滑动窗口特性设计。
- **`data_logger.py`**: 使用 `aiohttp` 异步每 30 秒抓取全港 MTR 站点数据。
- **`data_preparation_risk.py`**: 提取 MTR 数据的 `ttnt` 特征，利用反向滑动窗口（10步）生成初级任务的 `isdelay` 二分类标签。
- **`data_preparation_propagation.py`**: 聚合连续的 `isdelay="Y"` 时间块形成独立事件，生成高级任务的“持续时长”与“受影响车辆数”标签，并对稀有事件执行高斯噪声数据增强。
- **`train_delay_risk.py`**: 初级任务 GRU 训练脚本，使用 `BCELoss`。
- **`train_delay_propagation.py`**: 高级任务多输出 GRU 训练脚本，使用 `MSELoss`。
- **`inference/`**:
  - `spark_etl_mtr.py`: 利用 Spark RDD 提取 MTR JSON 快照特征，融合上下文后返回 DataFrame。
  - `predictor_mtr.py`: `MTRPredictor` 单例类，同时加载两套模型，执行批处理推理；内置了硬件降级机制与 MOCK 模式开关。

### 4. 后端 API 服务 (`src/api/`)
- **`main.py`**: FastAPI 应用入口。
  - 配置 `APScheduler` 在后台分别以 5 分钟（道路）和 15 秒（MTR）的频率触发 Spark ETL 与推理任务。
  - 提供 `/predict`, `/predictions`（道路）和 `/mtr/predictions`, `/mtr/delay-prediction`（MTR）等 RESTful 路由。
  - 利用静态文件挂载 (`StaticFiles`) 提供 `/map` 页面供浏览器访问。