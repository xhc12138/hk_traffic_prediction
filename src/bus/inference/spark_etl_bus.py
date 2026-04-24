import os
import sys
from pathlib import Path
from pyspark.sql import SparkSession
from pyspark.sql.functions import explode, col, collect_list, struct, to_json

project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(project_root))

def process_kmb_data(spark: SparkSession, stop_json_path: str, route_json_path: str):
    """
    Process KMB Bus data using Spark RDD/DataFrame.
    Reads stop and route-stop mapping JSONs and joins them.
    Returns aggregated JSON string ready for API response.
    """
    print("[BUS] Processing KMB data...")
    try:
        if not os.path.exists(stop_json_path) or not os.path.exists(route_json_path):
            print("[BUS] KMB JSON files not found. Skipping KMB processing.")
            return None
            
        # Read JSON
        kmb_stop = spark.read.option("multiline", "true").json(stop_json_path)
        kmb_route = spark.read.option("multiline", "true").json(route_json_path)
        
        # Explode the 'data' array
        if "data" in kmb_stop.columns:
            kmb_stop = kmb_stop.select(explode(col("data")).alias("stop_info"))
            kmb_stop = kmb_stop.select("stop_info.*")
            
        if "data" in kmb_route.columns:
            kmb_route = kmb_route.select(explode(col("data")).alias("route_info"))
            kmb_route = kmb_route.select("route_info.*")
            
        # Join route and stop
        kmb_data = kmb_route.join(kmb_stop, kmb_route.stop == kmb_stop.stop, "inner")
        
        # Since KMB routes can be huge, let's aggregate them by route and bound
        # so the frontend can easily digest them as lines with stations
        aggregated = kmb_data.groupBy("route", "bound").agg(
            collect_list(
                struct(
                    col("seq"),
                    col("name_en"),
                    col("name_tc"),
                    col("lat"),
                    col("long")
                )
            ).alias("stops")
        )
        
        # Convert to local JSON format (limit to a few routes for performance testing if needed)
        # For full dataset, collect() might be heavy, but it's an ETL task that outputs JSON
        result_json = aggregated.toJSON().collect()
        parsed_result = [eval(row) for row in result_json] # Safe because we control the schema
        
        print(f"[BUS] Successfully aggregated {len(parsed_result)} KMB route directions.")
        return parsed_result
    except Exception as e:
        print(f"[BUS] Error processing KMB data: {e}")
        return None

def process_gov_data(spark: SparkSession, stop_geojson_path: str, route_geojson_path: str):
    """
    Process Government Bus data using Spark RDD/DataFrame.
    Note: FB_ROUTE.gdb_converted.geojson is 1.5GB!
    We must use Spark's distributed nature carefully to avoid OOM.
    """
    print("[BUS] Processing GOV data (This might take a while due to 1.5GB GeoJSON)...")
    try:
        if not os.path.exists(stop_geojson_path) or not os.path.exists(route_geojson_path):
            print("[BUS] GOV GeoJSON files not found. Skipping GOV processing.")
            return None
            
        # Read the 1MB STOP file
        gov_stop = spark.read.option("multiline", "true").json(stop_geojson_path)
        if "features" in gov_stop.columns:
            gov_stop = gov_stop.select(explode(col("features")).alias("feature"))
            gov_stop = gov_stop.select(
                col("feature.properties").alias("stop_properties"),
                col("feature.geometry.coordinates").alias("coordinates")
            )
            
        # Read the 1.5GB ROUTE file
        # Using multiline=true on 1.5GB JSON can cause OOM on Driver node because the whole file is parsed into memory.
        # However, if it's line-delimited GeoJSON, we can drop multiline=true.
        # Assuming it's a standard FeatureCollection, multiline=true is required but dangerous.
        # We will attempt it, but for a 1.5GB file, a proper ETL pipeline should chunk it.
        # To prevent OOM during testing, we'll try standard read.
        print("[BUS] Loading 1.5GB Route Data...")
        gov_route_data = spark.read.option("multiline", "true").json(route_geojson_path)
        
        if "features" in gov_route_data.columns:
            gov_route = gov_route_data.select(explode(col("features")).alias("feature"))
            gov_route = gov_route.select(
                col("feature.properties").alias("properties"), 
                col("feature.geometry.coordinates").alias("coordinates")
            )
            # The member's code: explode(col("coordinates")).alias("coordinates")
            # This implies they want to match every single point of the route line with a stop point.
            # This will create a massive cross-product!
            gov_route = gov_route.withColumn("route_point", explode(col("coordinates")))
        else:
            gov_route = gov_route_data
            
        # Join based on matching coordinates
        # Note: Exact float matching on coordinates is risky in GIS, but we follow the provided logic.
        print("[BUS] Joining Route and Stop Data on coordinates...")
        gov_data = gov_route.join(gov_stop, gov_route.route_point == gov_stop.coordinates, "inner")
        
        # We'll just count it to prove the RDD/DataFrame DAG worked successfully
        row_count = gov_data.count()
        print(f"[BUS] Successfully joined GOV data. Matched points count: {row_count}")
        
        # We don't return the full joined dataset to API to avoid crashing the server.
        # We return a summary dictionary.
        return {"status": "success", "matched_stops": row_count}
        
    except Exception as e:
        print(f"[BUS] Error processing GOV data: {e}")
        return None

def run_bus_etl(spark: SparkSession, task: str = "kmb"):
    """
    Main entry point for Bus ETL.
    Can specify 'kmb', 'gov', or 'all'
    """
    print(f"[BUS] Starting Bus ETL Pipeline for task: {task}")
    
    data_dir = os.path.join(project_root, "data", "historical", "bus")
    
    kmb_stop_path = os.path.join(data_dir, "stop_kmb.json")
    kmb_route_path = os.path.join(data_dir, "route_kmb.json")
    
    gov_stop_path = os.path.join(data_dir, "STOP_BUS.gdb_converted.geojson")
    gov_route_path = os.path.join(data_dir, "FB_ROUTE.gdb_converted.geojson")
    
    result = {}
    
    if task in ["kmb", "all"]:
        kmb_result = process_kmb_data(spark, kmb_stop_path, kmb_route_path)
        if kmb_result:
            result["kmb"] = kmb_result
            
    if task in ["gov", "all"]:
        gov_result = process_gov_data(spark, gov_stop_path, gov_route_path)
        if gov_result:
            result["gov"] = gov_result
            
    print("[BUS] Bus ETL Pipeline Completed.")
    return result

if __name__ == "__main__":
    os.environ['PYSPARK_PYTHON'] = sys.executable
    os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable
    
    spark = SparkSession.builder \
        .appName("Bus Route ETL") \
        .master("local[*]") \
        .config("spark.driver.memory", "4g") \
        .config("spark.executor.memory", "4g") \
        .getOrCreate()
        
    # Test only KMB by default to avoid the 1.5GB GOV file OOM locally
    res = run_bus_etl(spark, "kmb")
    print(f"KMB Routes processed: {len(res.get('kmb', []))}")
    
    spark.stop()