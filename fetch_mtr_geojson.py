import urllib.request
import json
import os

url = "https://raw.githubusercontent.com/nathanielw/hong-kong-mtr-stations-geojson/master/mtr_lines_and_stations.json"
output_dir = "data/road_network/processed"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "mtr_network.geojson")

try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Successfully downloaded MTR GeoJSON to {output_path}")
except Exception as e:
    print(f"Failed to download from primary source: {e}")
    # Fallback to create a minimal dummy GeoJSON for stations we know
    print("Creating fallback MTR GeoJSON from config...")
    import yaml
    with open("config/local.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    # We don't have exact coordinates, but we can make a dummy structure
    # Just to let the frontend code work. In a real scenario we'd need exact coords.
    # Let's try another source if the first fails
    
    url2 = "https://raw.githubusercontent.com/CivicData/hong-kong-mtr-stations/master/mtr_lines_and_stations.geojson"
    try:
        req2 = urllib.request.Request(url2, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req2) as response:
            data = json.loads(response.read().decode())
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Successfully downloaded MTR GeoJSON from fallback to {output_path}")
    except Exception as e2:
        print(f"Failed fallback: {e2}")
        # Create a completely synthetic one for demonstration
        features = []
        lines_stas = config.get("mtr_lines_stations", {})
        
        # Rough coordinates for HK
        base_lat, base_lng = 22.3, 114.17
        offset = 0.01
        
        for line, stas in lines_stas.items():
            for i, sta in enumerate(stas):
                features.append({
                    "type": "Feature",
                    "properties": {
                        "line": line,
                        "sta": sta,
                        "name": f"{line}-{sta}"
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [base_lng + i*offset, base_lat + (hash(line)%10)*offset]
                    }
                })
        
        dummy = {
            "type": "FeatureCollection",
            "features": features
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(dummy, f, ensure_ascii=False, indent=2)
        print(f"Created synthetic MTR GeoJSON at {output_path}")
