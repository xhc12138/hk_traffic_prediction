import requests
import json

def test_endpoints():
    base_url = "http://127.0.0.1:8000"
    
    print("1. Testing /map_config...")
    try:
        r = requests.get(f"{base_url}/map_config")
        r.raise_for_status()
        print("✅ /map_config OK")
        print("  Response:", r.json())
    except Exception as e:
        print("❌ /map_config FAILED:", e)

    print("\n2. Testing /road_network...")
    try:
        r = requests.get(f"{base_url}/road_network")
        r.raise_for_status()
        geojson = r.json()
        print("✅ /road_network OK")
        print("  Feature count:", len(geojson.get("features", [])))
    except Exception as e:
        print("❌ /road_network FAILED:", e)

    print("\n3. Testing /predictions...")
    try:
        r = requests.get(f"{base_url}/predictions")
        r.raise_for_status()
        preds = r.json()
        print("✅ /predictions OK")
        print("  Prediction count:", preds.get("count"))
        
        # Test a single prediction
        if preds.get("count", 0) > 0:
            first_key = list(preds["predictions"].keys())[0]
            first_val = preds["predictions"][first_key]
            print(f"  Sample prediction: Segment {first_key} -> {first_val} mins")
    except Exception as e:
        print("❌ /predictions FAILED:", e)

    print("\n4. Testing /map (Frontend HTML)...")
    try:
        r = requests.get(f"{base_url}/map")
        r.raise_for_status()
        print("✅ /map OK")
        print("  Content type:", r.headers.get("Content-Type"))
        print("  Content starts with:", r.text[:50].replace('\n', ' '))
    except Exception as e:
        print("❌ /map FAILED:", e)

if __name__ == "__main__":
    test_endpoints()
