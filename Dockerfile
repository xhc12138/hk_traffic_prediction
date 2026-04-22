FROM python:3.10-slim

# Install Java for PySpark
RUN apt-get update && apt-get install -y openjdk-17-jre-headless && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install geopandas fiona pyogrio shapely
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

COPY . .

ENV ENV=cloud
EXPOSE 8000

CMD ["python", "src/api/main.py"]