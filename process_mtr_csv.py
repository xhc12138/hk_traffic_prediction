import pandas as pd
import json
import os
import yaml

stations = pd.read_csv("mtr-map-master/stations.csv")

name_to_code = {
    'Hong Kong': 'HOK', 'Kowloon': 'KOW', 'Tsing Yi': 'TSY', 'Airport': 'AIR', 'AsiaWorld-Expo': 'AWE',
    'Olympic': 'OLY', 'Nam Cheong': 'NAC', 'Lai King': 'LAK', 'Sunny Bay': 'SUN', 'Tung Chung': 'TUC',
    'Wu Kai Sha': 'WKS', 'Ma On Shan': 'MOS', 'Heng On': 'HEO', 'Tai Shui Hang': 'TSH', 'Shek Mun': 'SHM', 
    'City One': 'CIO', 'Sha Tin Wai': 'STW', 'Che Kung Temple': 'CKT', 'Tai Wai': 'TAW', 'Hin Keng': 'HIK',
    'Diamond Hill': 'DIH', 'Kai Tak': 'KAT', 'Sung Wong Toi': 'SUW', 'To Kwa Wan': 'TKW', 'Ho Man Tin': 'HOM', 
    'Hung Hom': 'HUH', 'East Tsim Sha Tsui': 'ETS', 'Austin': 'AUS', 'Mei Foo': 'MEF', 'Tsuen Wan West': 'TWW',
    'Kam Sheung Road': 'KSR', 'Yuen Long': 'YUL', 'Long Ping': 'LOP', 'Tin Shui Wai': 'TIS', 'Siu Hong': 'SIH', 
    'Tuen Mun': 'TUM', 'North Point': 'NOP', 'Quarry Bay': 'QUB', 'Yau Tong': 'YAT', 'Tiu Keng Leng': 'TIK',
    'Tseung Kwan O': 'TKO', 'LOHAS Park': 'LHP', 'Hang Hau': 'HAH', 'Po Lam': 'POA', 'Admiralty': 'ADM',
    'Exhibition Centre': 'EXC', 'Mong Kok East': 'MKK', 'Kowloon Tong': 'KOT', 'Sha Tin': 'SHT', 'Fo Tan': 'FOT', 
    'Racecourse': 'RAC', 'University': 'UNI', 'Tai Po Market': 'TAP', 'Tai Wo': 'TWO', 'Fanling': 'FAN', 
    'Sheung Shui': 'SHS', 'Lo Wu': 'LOW', 'Lok Ma Chau': 'LMC', 'Ocean Park': 'OCP', 'Wong Chuk Hang': 'WCH', 
    'Lei Tung': 'LET', 'South Horizons': 'SCH', 'Central': 'CEN', 'Tsim Sha Tsui': 'TST', 'Jordan': 'JOR', 
    'Yau Ma Tei': 'YMT', 'Mong Kok': 'MOK', 'Prince Edward': 'PRE', 'Sham Shui Po': 'SSP', 'Cheug Sha Wan': 'CSW', 
    'Lai Chi Kok': 'LCK', 'Kwai Fong': 'KWF', 'Kwai Hing': 'KWH', 'Tai Wo Hau': 'TWH', 'Tsuen Wan': 'TSW',
    'Kennedy Town': 'KET', 'HKU': 'HKU', 'Sai Ying Pun': 'SYP', 'Sheung Wan': 'SHW', 'Wan Chai': 'WAC', 
    'Causeway Bay': 'CAB', 'Tin Hau': 'TIH', 'Fortress Hill': 'FOH', 'Tai Koo': 'TAK', 'Sai Wan Ho': 'SWH', 
    'Shau Kei Wan': 'SKW', 'Heng Fa Chuen': 'HFC', 'Chai Wan': 'CHW', 'Whampoa': 'WHA', 'Shek Kip Mei': 'SKM', 
    'Lok Fu': 'LOF', 'Wong Tai Sin': 'WTS', 'Choi Hung': 'CHH', 'Kowloon Bay': 'KOB', 'Ngau Tau Kok': 'NTK', 
    'Kwun Tong': 'KWT', 'Lam Tin': 'LAT', 'Disneyland Resort': 'DIS'
}

# In the mtr-map-master, x_real and y_real are pixel coordinates on a static map, not geographic coordinates.
# To render them in Leaflet properly without a custom CRS, we need to map them back to EPSG:4326 (Lon, Lat).
# We can do an affine transformation from the bounding box of x_real/y_real to the bounding box of HK MTR.
# Actual HK MTR bounds (roughly):
# Longitude: 113.93 (Airport) to 114.27 (LOHAS Park)
# Latitude: 22.24 (South Horizons) to 22.53 (Lo Wu)

min_x, max_x = stations['x_real'].min(), stations['x_real'].max()
min_y, max_y = stations['y_real'].min(), stations['y_real'].max()

# Tuen Mun is roughly 113.97, 22.39. Let's find the exact ones to create a linear model.
# Since it's a simple project, let's use min/max mapping.
lon_min, lon_max = 113.93, 114.27
lat_min, lat_max = 22.53, 22.24 # Note: y in SVG goes DOWN, so min_y is North (High Lat)

def map_lon(x):
    return lon_min + (x - min_x) / (max_x - min_x) * (lon_max - lon_min)

def map_lat(y):
    return lat_max + (y - max_y) / (min_y - max_y) * (lat_min - lat_max)

stations['lon'] = stations['x_real'].apply(map_lon)
stations['lat'] = stations['y_real'].apply(map_lat)

stations['sta_code'] = stations['name'].map(name_to_code)

output_dir = "data/road_network/processed"
os.makedirs(output_dir, exist_ok=True)

with open("config/local.yaml", "r") as f:
    config = yaml.safe_load(f)

lines_stas = config.get("mtr_lines_stations", {})

line_colors = {
    "AEL": "#008784", "TCL": "#F8912E", "TML": "#995025", "TKL": "#88509F", "EAL": "#5DB7DE",
    "SIL": "#B1CA27", "TWL": "#E2231A", "ISL": "#0071CE", "KTL": "#00AB4E", "DRL": "#E6005C"
}

features = []

# Generate LineStrings
for line, stas in lines_stas.items():
    coords = []
    for sta in stas:
        row = stations[stations['sta_code'] == sta]
        if not row.empty:
            coords.append([row.iloc[0]['lon'], row.iloc[0]['lat']])
            
    if len(coords) > 1:
        features.append({
            "type": "Feature",
            "properties": {
                "line": line,
                "type": "LineString",
                "color": line_colors.get(line, "#000000")
            },
            "geometry": {
                "type": "LineString",
                "coordinates": coords
            }
        })

# Generate Points
for _, row in stations.dropna(subset=['sta_code']).iterrows():
    # Find which line this belongs to (can be multiple, we just assign the first found)
    assigned_line = "UNKNOWN"
    for line, stas in lines_stas.items():
        if row['sta_code'] in stas:
            assigned_line = line
            break
            
    features.append({
        "type": "Feature",
        "properties": {
            "line": assigned_line,
            "sta": row['sta_code'],
            "name": f"{assigned_line}-{row['sta_code']}",
            "type": "Point",
            "color": line_colors.get(assigned_line, "#000000")
        },
        "geometry": {
            "type": "Point",
            "coordinates": [row['lon'], row['lat']]
        }
    })

geojson = {
    "type": "FeatureCollection",
    "features": features
}

output_path = os.path.join(output_dir, "mtr_network.geojson")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(geojson, f, ensure_ascii=False, indent=2)

print(f"Successfully generated {output_path} from mtr-map-master/stations.csv")

