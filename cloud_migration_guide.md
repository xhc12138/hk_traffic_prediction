# 云端迁移指导文档 (Cloud Migration Guide)

本项目目前在本地开发环境中运行良好，但其核心架构（特别是 Spark ETL 与 PyTorch 推理）完全是为了云端大数据处理和分布式计算而设计的。本指南将详细说明项目中哪些部分使用了云服务相关功能，以及如何将整个项目平滑迁移到 AWS / Azure 等云端环境。

## 1. 现有的云端架构适配点

在开发阶段，我们已经在代码中埋入了多个云端迁移的“锚点”，实现了 **Local** 与 **Cloud** 环境的零代码修改切换：

### 1.1 Config-Driven (配置驱动)
项目的所有环境依赖项都提取到了 `config/` 目录下。
- **`config/local.yaml`**：使用 `master: "local[*]"`，在单机上利用所有 CPU 核心模拟 Spark 集群。
- **`config/cloud.yaml`**：预留了真实的 Spark Master URL（如 `master: "spark://<YOUR-SPARK-MASTER-IP>:7077"`），并在部署时通过环境变量 `ENV=cloud` 自动加载。

### 1.2 PySpark RDD 集群处理
在 `src/inference/spark_etl.py` 和 `src/mtr/inference/spark_etl_mtr.py` 中，实时拉取的庞大 XML/JSON 数据被设计为通过 Spark 的 RDD 进行分布式解析：
```python
rdd = spark.sparkContext.parallelize([json_content])
parsed_rdd = rdd.flatMap(parse_json_partition)
```
当迁移到云端 Spark 集群时，这部分代码无需修改，它会自动将数据分片派发到各个 Worker 节点并行处理。

### 1.3 容器化准备 (Docker)
项目根目录下已经提供了一个 `Dockerfile`，它基于 `python:3.10-slim`，内置了 Java 17 运行时（供 PySpark 使用）以及 PyTorch 的 CUDA 12.1 依赖。这使得 FastAPI 服务可以直接部署到 ECS、EKS、Kubernetes 等容器编排平台上。

### 1.4 GPU 自动降级容错
在 `src/train.py` 和 `src/mtr/inference/predictor_mtr.py` 中，如果云端服务器没有配置昂贵的 GPU，或者 CUDA 驱动版本不匹配，代码会自动捕获 `RuntimeError` 并优雅地回退到 CPU 推理：
```python
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
try:
    torch.zeros(1).to(device)
except RuntimeError:
    device = torch.device('cpu')
```
这极大地降低了云端实例的选择成本。

---

## 2. 迁移到云端的步骤指导

### 步骤 1：部署 Spark 集群 (Spark Standalone / EMR)
由于实时数据处理依赖 Spark ETL，你需要在云端准备一个 Spark 环境。
1. **选项 A (简单)**：购买一台大内存的 EC2 / 虚拟机，安装 Java 和 Spark，启动一个 Standalone Master 和几个 Worker。
2. **选项 B (生产级)**：使用 AWS EMR 或 Dataproc，创建一个托管的 Spark 集群。
3. **更新配置**：获取 Spark Master 的内网/公网 IP，打开项目的 `config/cloud.yaml`，将 `master` 字段更新为该 IP，例如 `spark://10.0.1.25:7077`。

### 步骤 2：云端存储挂载 (S3 / 对象存储)
本地的 `data/models/` 包含了数十 MB 的 PyTorch 权重文件（如 `best_model.pth`）。在云端，不建议将大文件打包进 Docker 镜像。
1. 将本地训练好的 `.pth` 和 `.parquet` 文件上传到 S3 存储桶。
2. 在云端服务器启动前，通过启动脚本（或 boto3）自动将这些文件下载到容器的 `data/models/` 目录下，或者直接通过 FUSE 将 S3 挂载为本地目录。

### 步骤 3：构建并推送 Docker 镜像
在本地或 CI/CD 流水线中构建 Docker 镜像：
```bash
docker build -t hk-traffic-prediction:latest .
```
将镜像推送到云端的容器镜像仓库（如 AWS ECR, Docker Hub）。

### 步骤 4：前端静态资源 CDN 部署 (可选但推荐)
尽管 FastAPI 可以通过 `StaticFiles` 挂载 `frontend/` 目录和 `data/road_network/` 目录来直接提供 HTML、JS 和 GeoJSON 地图数据，但在生产环境中，更推荐以下架构以降低 API 服务器的带宽压力：
1. 将 `frontend/` 文件夹内的 HTML/CSS/JS 文件，以及庞大的地图数据 (`road_network.geojson`, `mtr_network.geojson`) 提取出来。
2. 上传到云端的 CDN 或对象存储服务（如 AWS S3 + CloudFront, Aliyun OSS）。
3. 修改前端 `map.js` 中的数据拉取 URL（将原先的相对路径 `/road_network` 改为 S3 URL），并将后端的 RESTful 预测接口（如 `http://<API-IP>:8000/predictions`）以环境变量的形式注入前端。

### 步骤 5：启动后端 API 服务
在云端服务器（或 Kubernetes Pod）上拉取镜像并运行。Docker 内部已经默认将环境变量 `ENV` 设置为 `cloud`，所以服务会自动加载 `cloud.yaml` 的配置，并连接到你在步骤 1 中准备的 Spark 集群。
```bash
docker run -d \
  -p 80:8000 \
  -e ENV=cloud \
  --name traffic_api \
  hk-traffic-prediction:latest
```

### 步骤 6：独立提交 Spark 推理任务 (可选)
如果你的数据量达到 TB 级别，导致 FastAPI 内部的单例 Spark Session 成为瓶颈，你可以使用项目中提供的 `spark-submit-inference.sh`，将其配置为云端 CronJob 或 Airflow 任务，直接向 Spark 集群提交分布式的批处理脚本。

## 3. 验收与健康检查
服务在云端启动后，可以通过访问公网 IP 进行健康检查：
```bash
curl -s http://<CLOUD-IP>:80/
```
如果返回 `{"status": "Success"}`，说明 FastAPI 与 Spark 集群、PyTorch 模型的连接均已在云端打通，前端 Dashboard 可以将请求地址修改为该云端 IP 即可。