import requests
import json
import time
import sys

BASE_URL = "http://127.0.0.1:8000"

def print_separator(title):
    print(f"\n{'='*50}")
    print(f"--- {title} ---")
    print(f"{'='*50}")

def check_status(response):
    if response.status_code == 200:
        print("✅ Status Code: 200 OK")
        return True
    else:
        print(f"❌ Error: Received status code {response.status_code}")
        return False

def test_api_endpoint(method, endpoint, params=None):
    url = f"{BASE_URL}{endpoint}"
    print(f"Testing: {method} {url}")
    if params:
        print(f"Params: {params}")
        
    try:
        start_time = time.time()
        if method == "GET":
            response = requests.get(url, params=params)
        else:
            print(f"Method {method} not implemented in test script.")
            return False
            
        elapsed_time = time.time() - start_time
        
        if check_status(response):
            print(f"⏱️  Response Time: {elapsed_time:.3f} seconds")
            try:
                data = response.json()
                print("📦 Response Data Preview (first 200 chars):")
                data_str = json.dumps(data, ensure_ascii=False)
                if len(data_str) > 200:
                    print(f"{data_str[:200]}...")
                else:
                    print(data_str)
                return True
            except json.JSONDecodeError:
                print("❌ Error: Response is not valid JSON")
                print(f"Content: {response.text[:200]}")
                return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Error: Connection failed. Is the API server running at {BASE_URL}?")
        return False
    except Exception as e:
        print(f"❌ Error: An unexpected error occurred: {e}")
        return False

def run_all_tests():
    print("Starting API Tests for HK Traffic & MTR Prediction System...")
    
    # Test Root
    print_separator("Root & Config Endpoints")
    test_api_endpoint("GET", "/")
    test_api_endpoint("GET", "/map_config")
    
    # Test Road Traffic Endpoints
    print_separator("Road Traffic Prediction Endpoints")
    test_api_endpoint("GET", "/predictions")
    # Using a common segment_id for testing (e.g., 105500)
    test_api_endpoint("GET", "/predict", params={"segment_id": 105500})
    
    # Test MTR Prediction Endpoints
    print_separator("MTR Delay Prediction Endpoints")
    # Batch risk prediction
    test_api_endpoint("GET", "/mtr/predictions")
    # Single station risk prediction
    test_api_endpoint("GET", "/mtr/predictions", params={"line": "TCL", "sta": "OLY"})
    
    # Batch propagation prediction
    test_api_endpoint("GET", "/mtr/delay-prediction")
    # Single station propagation prediction
    test_api_endpoint("GET", "/mtr/delay-prediction", params={"line": "TCL", "sta": "OLY"})
    
    print("\n✅ All API endpoint tests completed.")

if __name__ == "__main__":
    run_all_tests()