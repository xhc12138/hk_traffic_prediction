import os
import sys
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, IntegerType, FloatType, StringType
from lxml import etree
import requests
import pandas as pd
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from src.utils.config import config
from src.utils.helpers import extract_time_features

def create_spark_session():
    os.environ['PYSPARK_PYTHON'] = sys.executable
    os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable
    
    master = config.get('master', 'local[*]')
    spark = SparkSession.builder \
        .appName("TrafficCongestionInference") \
        .master(master) \
        .getOrCreate()
    return spark

def fetch_realtime_xml():
    url = config.get('realtime_url')
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"Error fetching realtime XML: {e}")
        return None

def parse_xml_partition(xml_content):
    """Parse the XML content to list of dicts. Used in map/flatMap"""
    if not xml_content:
        return []
    
    try:
        tree = etree.fromstring(xml_content)
        date_elem = tree.find('date')
        time_elem = tree.find('time')
        
        if date_elem is None or time_elem is None:
            return []
            
        record_date = date_elem.text
        record_time = time_elem.text
        
        segments = tree.find('segments')
        if segments is None:
            return []
            
        data = []
        for segment in segments.findall('segment'):
            seg_id = segment.find('segment_id')
            speed = segment.find('speed')
            valid = segment.find('valid')
            
            if seg_id is not None and speed is not None and valid is not None:
                if valid.text == 'Y':
                    data.append({
                        'date': record_date,
                        'time': record_time,
                        'segment_id': int(seg_id.text),
                        'speed': float(speed.text)
                    })
        return data
    except Exception as e:
        print(f"Parse error: {e}")
        return []

def run_spark_etl(spark, xml_content):
    """
    Process XML using Spark RDDs.
    """
    if not xml_content:
        return pd.DataFrame()
        
    # Use RDD to parallelize XML parsing (though it's a single file here, 
    # we wrap it in a list to demonstrate RDD usage for ETL as requested)
    rdd = spark.sparkContext.parallelize([xml_content])
    
    # map/flatMap to parse features
    parsed_rdd = rdd.flatMap(parse_xml_partition)
    
    # Collect to local since we just need the dataframe for the predictor
    # For large scale, we'd use Spark SQL DataFrames
    data = parsed_rdd.collect()
    
    if not data:
        return pd.DataFrame()
        
    df = pd.DataFrame(data)
    
    # Feature engineering using pandas locally after ETL aggregation
    df = extract_time_features(df)
    
    return df

if __name__ == '__main__':
    spark = create_spark_session()
    xml = fetch_realtime_xml()
    df = run_spark_etl(spark, xml)
    print(df.head())
    spark.stop()