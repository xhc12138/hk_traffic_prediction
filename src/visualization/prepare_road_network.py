import os
import sys
from pathlib import Path
import geopandas as gpd
import pandas as pd

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from src.utils.config import config

def main():
    print("Starting road network preprocessing...")
    
    # 1. Load configuration paths
    raw_gdb_path = os.path.join(project_root, 'data/road_network/raw/RdNet_IRNP.gdb')
    processed_data_path = os.path.join(project_root, config.get('data_path', 'data/processed/train_data.parquet'))
    
    # Get config for output, default to data/road_network/processed/road_network.geojson
    output_path = os.path.join(project_root, config.get('road_network_geojson_path', 'data/road_network/processed/road_network.geojson'))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 2. Read unique segment IDs from processed training data
    print(f"Reading training data from {processed_data_path} to find valid segment_ids...")
    try:
        df_train = pd.read_parquet(processed_data_path, columns=['segment_id'])
        valid_segments = df_train['segment_id'].unique()
        print(f"Found {len(valid_segments)} unique segment_ids.")
    except Exception as e:
        print(f"Error reading training data: {e}")
        print("Cannot filter roads without valid segment_ids. Exiting.")
        return

    # 3. Read road network CENTERLINE from FGDB
    print(f"Reading road network CENTERLINE from {raw_gdb_path}...")
    if not os.path.exists(raw_gdb_path):
        print(f"Error: {raw_gdb_path} does not exist. Please download and extract RdNet_IRNP.gdb.zip first.")
        return
        
    gdf_roads = gpd.read_file(raw_gdb_path, layer='CENTERLINE')
    print(f"Total road segments in FGDB: {len(gdf_roads)}")
    
    # 4. Filter, rename, and select columns
    print("Filtering road segments to match prediction dataset...")
    # 'ROUTE_ID' corresponds to 'segment_id' in our dataset
    gdf_filtered = gdf_roads[gdf_roads['ROUTE_ID'].isin(valid_segments)].copy()
    
    # Rename ROUTE_ID to segment_id for consistency
    gdf_filtered = gdf_filtered.rename(columns={'ROUTE_ID': 'segment_id'})
    
    # Keep only necessary columns to reduce file size
    cols_to_keep = ['segment_id', 'STREET_ENAME', 'geometry']
    gdf_filtered = gdf_filtered[cols_to_keep]
    print(f"Filtered down to {len(gdf_filtered)} major road segments.")
    
    # 5. Coordinate transformation to EPSG:4326 (WGS84) for web mapping
    print("Reprojecting coordinates to EPSG:4326 (WGS84)...")
    gdf_filtered = gdf_filtered.to_crs("EPSG:4326")
    
    # 6. Simplify geometry slightly to reduce file size (optional, tolerance in degrees)
    print("Simplifying geometries...")
    # 0.00005 degrees is roughly 5 meters
    gdf_filtered['geometry'] = gdf_filtered['geometry'].simplify(0.00005, preserve_topology=True)
    
    # 7. Save to GeoJSON
    print(f"Saving processed GeoJSON to {output_path}...")
    # Remove if exists to avoid errors
    if os.path.exists(output_path):
        os.remove(output_path)
        
    gdf_filtered.to_file(output_path, driver='GeoJSON')
    
    # Get file size
    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"Done! GeoJSON saved successfully. Size: {file_size_mb:.2f} MB")

if __name__ == "__main__":
    main()
