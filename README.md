# 香港交通预测与港铁延误预警系统

本项目是一个基于 Spark RDD (大数据实时提取) 与 PyTorch (深度学习推理) 构建的**香港交通拥堵预测与 MTR 延误预警后端服务**，专为提供高性能、高并发的 RESTful JSON 接口给前端 Web/Dashboard 团队对接而设计。

本项目由两个核心子模块组成：

1. **Road Traffic Prediction (道路交通拥堵预测)**
2. **MTR Delay Prediction (港铁延误风险与影响传播预测)**

***

## 📚 项目技术文档索引

为了让协作者更好地理解系统架构，本项目附带了详尽的设计文档：

- [项目文件架构与各文件作用详解 (project\_structure.md)](project_structure.md)
- [道路交通预测功能详解 (road\_traffic\_prediction.md)](road_traffic_prediction.md)
- [港铁延误预测功能详解 (mtr\_delay\_prediction.md)](mtr_delay_prediction.md)
- [云端迁移与集群部署指导文档 (cloud\_migration\_guide.md)](cloud_migration_guide.md)
- 项目综合介绍文档（ppt和报告的大纲）project\_presentation\_guide.md

***

## 🚀 快速启动指南 (面向新协作者与部署者)

本指南针对**只需运行后端服务并提供 API**的协作者。你不需要执行漫长的模型训练，只需配置好基础环境并拉起服务即可。

### 1. 环境配置

本项目依赖于 Python 3.10、Java 17 (PySpark 必需) 以及支持 CUDA 的 PyTorch。
推荐使用 Conda 进行环境隔离：

```bash
# 1. 创建并激活 Conda 虚拟环境
conda create -y -n hk_traffic python=3.10
conda activate hk_traffic

# 2. 安装 Java 17 (Linux 环境，供 PySpark 运行)
conda install -y -c conda-forge openjdk=17

# 3. 安装 Python 核心依赖与 PyTorch (CUDA 12.1 稳定版)
pip install -r requirements.txt
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

*(注：系统内置了极强的防宕机设计。如果你的机器没有 GPU，或者 GPU 驱动版本不匹配，代码会自动捕获异常并平滑降级至纯 CPU 推理模式，无需担心运行崩溃。)*

### 2. 启动全局 API 与地图服务

在项目根目录下执行提供的一键启动脚本。
默认情况下，服务会在后台加载已训练好的 `data/models/` 权重，并通过 APScheduler 每隔一段时间（道路5分钟，港铁15秒）自动从政府 Open Data 接口拉取真实数据、送入 Spark 管道并更新缓存。

```bash
# --real 参数表示加载真实的 PyTorch 模型，而不是返回随机 Mock 数据
bash run_local.sh --real
```

**启动成功的标志：**
你会看到终端打印出模型加载信息、硬件识别信息，并在最后显示：

```text
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

此时，你的后端服务已在本地 `8000` 端口就绪！

***

## 🗺️ Web 前端双系统 Dashboard (地图监控)

如果你是负责前端对接或系统验收的组员，本项目已经内置了一个强大的可视化测试页面：

- **打开浏览器访问**：`http://127.0.0.1:8000/map`
- **双系统无缝切换**：点击页面右上角的 `Road Traffic System` 和 `MTR Delay System` 按钮，可以在公路拥堵监控和港铁延误预警两套大屏之间自由切换。
- **实时预警动画**：
  - **道路交通**：所有干道会根据拥堵程度渲染为绿/黄/橙/红色，并支持点击查询。
  - **港铁预警**：悬停 (Hover) 站点即可查看下一班车的等候时间；当地铁发生延误时（由后端高级任务预测判定），地图上的站点会**闪烁红光**，同时左侧下方的“事件面板”会列出详细的受波及情况（例如：*影响3班列车，预计延误15分钟*），点击列表更可自动缩放定位到该事故车站。

***

## 🧪 自动化接口测试

为了确认你的后端服务启动无误并且所有路由均能正常响应，你可以运行项目中提供的自动化测试脚本：

```bash
# 在另一个终端窗口运行
python test_api.py
```

该脚本将模拟前端发起 HTTP GET 请求，测试 `/predictions`、`/mtr/delay-prediction` 等核心接口，并打印出每个接口的**状态码、响应时间以及 JSON 预览**。如果所有测试均返回 `✅ Status Code: 200 OK`，则说明你的服务部署完美成功。

***

## 📡 接口调用文档 (API Reference)

前端开发人员或 Dashboard 协作者可以直接调用以下 `http://127.0.0.1:8000` 暴露的 JSON 接口。

### 1. 全局基础接口

- **GET** **`/`**：返回服务状态、欢迎信息及可用端点列表。
- **GET** **`/map_config`**：获取前端地图渲染所需的配置（中心坐标、警示颜色阈值等）。

### 2. 道路交通拥堵预测 (Road Traffic)

后台每 5 分钟更新一次。

- **GET** **`/predictions`**：批量获取全港数千个干道 `segment_id` 的未来阻塞时长（分钟）。适合地图全局染色。
- **GET** **`/predict?segment_id=105500`**：获取特定路段的详细预测时长。适合点击路段时弹出的信息气泡。

### 3. 港铁延误预警 (MTR Delay)

后台每 15 秒更新一次。

- **GET** **`/mtr/predictions`**：批量获取 10 条线路 100+ 站点的初级任务结果：**延误风险概率** (0\~1)。
- **GET** **`/mtr/delay-prediction`**：批量获取全量站点的**高级系统级预测**。
  - 回传 JSON 中包含了：`delay_risk_probability` (风险)、`delay_duration_minutes` (预计持续分钟)、`affected_trains_count` (预计受影响车次) 以及用于前端渲染的 `color_code` (绿/黄/红)。
- **单一站点查询示例**：`GET /mtr/delay-prediction?line=TCL&sta=OLY`

> **前端轮询对接建议 (JavaScript)**：
> 前端无需关心数据拉取和推理逻辑，只需使用 `setInterval` 定时（如道路 5 分钟，MTR 15 秒）对 `/predictions` 和 `/mtr/delay-prediction` 发起 `fetch()` 请求，即可始终获取内存中最新的预测状态并实时更新仪表板。

***

## ☁️ 云端部署简述

本项目完全支持平滑迁移至 AWS / 阿里云等云端环境。
只需修改环境变量 `ENV=cloud`，系统会自动读取 `config/cloud.yaml` 中的配置，并连接到分布式的 Spark Master 节点。
更详细的 Docker 容器化构建、S3 模型挂载与 Spark RDD 集群适配指南，请参阅 [cloud\_migration\_guide.md](cloud_migration_guide.md)。
