# 道路交通预测功能详解 (Road Traffic Prediction)

## 1. 核心目标
本功能旨在提供一个基于 Spark RDD 和 PyTorch 的**香港主要干道交通阻塞时间预测模块**。通过实时获取香港运输署的 `irnAvgSpeed-all.xml` 接口数据，结合历史路况数据，本模块能够预测未来 30 分钟内各主要路段的阻塞情况（以分钟为单位），并将结果通过 RESTful API 提供给前端地图应用（如 Dashboard）。

## 2. 数据处理与特征工程

### 2.1 数据源
- **历史数据**：存储在 `data/historical/processed/*.xml`。
- **实时数据**：通过接口 `https://resource.data.one.gov.hk/td/traffic-detectors/irnAvgSpeed-all.xml` 每 5 分钟拉取一次。

### 2.2 特征提取 (`src/utils/helpers.py`)
为了捕捉交通模式的周期性，我们对时间戳进行了丰富的特征工程：
- **时间特征**：提取当前 `hour` (小时)。
- **日期特征**：提取 `day_of_week` (星期几)。
- **周末与高峰标识**：
  - `is_weekend`: 标示是否为周六或周日。
  - `is_peak`: 标示是否处于早高峰 (07:00-09:00) 或晚高峰 (17:00-19:00)。
- **车速缩放**：原始车速被缩放 (除以 100.0) 以帮助神经网络更好地收敛。

### 2.3 标签生成 (`src/data_preparation.py`)
预测目标设定为**阻塞持续时间**。
- 阻塞定义为车速 `< 30 km/h` 且持续 `>= 10 分钟`。
- 我们计算连续的拥堵事件（block），并求出累计阻塞分钟数，作为监督学习的 Target (`label_congestion_minutes`)。

## 3. 模型架构与训练 (`src/train.py`)

### 3.1 网络结构
采用纯 PyTorch 实现的 **GRU (Gated Recurrent Unit)** 模型 (`TrafficGRU`)。
- **输入层 (Input)**：接收形状为 `[Batch Size, Sequence Length (12), 5]` 的张量。这 5 个特征为 `[speed, hour, day_of_week, is_weekend, is_peak]`。
- **循环层 (RNN)**：2 层 Hidden Size 为 64 的 GRU，能够有效捕捉交通流的时间序列依赖。
- **输出层 (Output)**：一个线性全连接层 (Linear)，输出一个标量值，即预测的未来阻塞时间。

### 3.2 训练流程
- 序列长度设为 12（由于数据间隔约为 5 分钟，12 个步长刚好代表过去的 60 分钟）。
- 使用 **MSELoss** 作为损失函数，**Adam** 作为优化器。
- 支持 GPU 训练加速。若环境中无 GPU 或 CUDA 版本不兼容（如 RTX 5000 系等新架构尚未被默认 wheel 支持时），代码内置了**自动降级 (Fallback) 到 CPU** 的容错机制。

## 4. 实时推理管道 (Inference Pipeline)

推理阶段的设计严格遵循了**大数据扩展性**的原则，强制使用 Spark RDD 处理实时 XML。

### 4.1 Spark ETL (`src/inference/spark_etl.py`)
- 利用 PySpark 的 `SparkSession` 和 `RDD` 机制。
- 将实时拉取的巨大 XML 字符串切片并反序列化。通过 `flatMap` 提取每个有效 `segment_id` 的最新车速数据。
- 输出为轻量级的 Pandas DataFrame 交由预测器处理。

### 4.2 批量预测 (`src/inference/predictor.py`)
- 加载已训练好的最佳模型权重 (`data/models/best_model.pth`)。
- 采用 **Numpy / Tensor 批量处理 (Batch Inference)** 策略，而非低效的 for 循环。这极大提高了推理速度。
- 预测结果被限制为非负数 (`max(0.0, pred)`)。

## 5. API 暴露与定时任务 (`src/api/main.py`)
- 使用 **FastAPI** 搭建轻量级高性能 Web 服务。
- 使用 **APScheduler**，每隔 5 分钟触发一次完整流程（Fetch XML -> Spark ETL -> PyTorch Predict），并将结果缓存在内存字典中 (`latest_predictions`)。
- 提供了 `/predictions`（全局所有路段查询）和 `/predict?segment_id=XXX`（单一查询）供前端轮询，实现无缝动态更新。