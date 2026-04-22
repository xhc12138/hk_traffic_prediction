#!/usr/bin/env python3
import csv
import json
from collections import defaultdict
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MTR_MAP_DIR = PROJECT_ROOT / "mtr-map-master"
CONFIG_PATH = PROJECT_ROOT / "config" / "local.yaml"
OUTPUT_PATH = PROJECT_ROOT / "frontend" / "assets" / "mtr_topology.json"


LINE_META = {
    "AEL": {"name": "Airport Express", "color": "#00888A", "assets": ["airportexpress", "airportexpress_shared_section"]},
    "TCL": {"name": "Tung Chung Line", "color": "#F7943E", "assets": ["tungchungline"]},
    "TML": {"name": "Tuen Ma Line", "color": "#8B5E3C", "assets": ["Tuen_Ma_line"]},
    "TKL": {"name": "Tseung Kwan O Line", "color": "#7D499D", "assets": ["tseungkwanoline", "lohasparkspur"]},
    "EAL": {"name": "East Rail Line", "color": "#53B7E8", "assets": ["eastrailmain", "lokmachauspur", "racecoursespur"]},
    "SIL": {"name": "South Island Line", "color": "#B5BD00", "assets": ["southislandline"]},
    "TWL": {"name": "Tsuen Wan Line", "color": "#E2231A", "assets": ["tsuenwanline"]},
    "ISL": {"name": "Island Line", "color": "#007DC5", "assets": ["islandline"]},
    "KTL": {"name": "Kwun Tong Line", "color": "#00AB4E", "assets": ["kwuntongline"]},
    "DRL": {"name": "Disneyland Resort Line", "color": "#D61A7F", "assets": ["disneyline"]},
}

NAME_TO_CODE = {
    "Hong Kong": "HOK",
    "Kowloon": "KOW",
    "Tsing Yi": "TSY",
    "Airport": "AIR",
    "AsiaWorld-Expo": "AWE",
    "Olympic": "OLY",
    "Nam Cheong": "NAC",
    "Lai King": "LAK",
    "Sunny Bay": "SUN",
    "Tung Chung": "TUC",
    "Wu Kai Sha": "WKS",
    "Ma On Shan": "MOS",
    "Heng On": "HEO",
    "Tai Shui Hang": "TSH",
    "Shek Mun": "SHM",
    "City One": "CIO",
    "Sha Tin Wai": "STW",
    "Che Kung Temple": "CKT",
    "Tai Wai": "TAW",
    "Hin Keng": "HIK",
    "Diamond Hill": "DIH",
    "Kai Tak": "KAT",
    "Sung Wong Toi": "SUW",
    "To Kwa Wan": "TKW",
    "Ho Man Tin": "HOM",
    "Hung Hom": "HUH",
    "East Tsim Sha Tsui": "ETS",
    "Austin": "AUS",
    "Mei Foo": "MEF",
    "Tsuen Wan West": "TWW",
    "Kam Sheung Road": "KSR",
    "Yuen Long": "YUL",
    "Long Ping": "LOP",
    "Tin Shui Wai": "TIS",
    "Siu Hong": "SIH",
    "Tuen Mun": "TUM",
    "North Point": "NOP",
    "Quarry Bay": "QUB",
    "Yau Tong": "YAT",
    "Tiu Keng Leng": "TIK",
    "Tseung Kwan O": "TKO",
    "LOHAS Park": "LHP",
    "Hang Hau": "HAH",
    "Po Lam": "POA",
    "Admiralty": "ADM",
    "Exhibition Centre": "EXC",
    "Mong Kok East": "MKK",
    "Kowloon Tong": "KOT",
    "Sha Tin": "SHT",
    "Fo Tan": "FOT",
    "Racecourse": "RAC",
    "University": "UNI",
    "Tai Po Market": "TAP",
    "Tai Wo": "TWO",
    "Fanling": "FAN",
    "Sheung Shui": "SHS",
    "Lo Wu": "LOW",
    "Lok Ma Chau": "LMC",
    "Ocean Park": "OCP",
    "Wong Chuk Hang": "WCH",
    "Lei Tung": "LET",
    "South Horizons": "SCH",
    "Central": "CEN",
    "Tsim Sha Tsui": "TST",
    "Jordan": "JOR",
    "Yau Ma Tei": "YMT",
    "Mong Kok": "MOK",
    "Prince Edward": "PRE",
    "Sham Shui Po": "SSP",
    "Cheug Sha Wan": "CSW",
    "Cheung Sha Wan": "CSW",
    "Lai Chi Kok": "LCK",
    "Kwai Fong": "KWF",
    "Kwai Hing": "KWH",
    "Tai Wo Hau": "TWH",
    "Tsuen Wan": "TSW",
    "Kennedy Town": "KET",
    "HKU": "HKU",
    "Sai Ying Pun": "SYP",
    "Sheung Wan": "SHW",
    "Wan Chai": "WAC",
    "Causeway Bay": "CAB",
    "Tin Hau": "TIH",
    "Fortress Hill": "FOH",
    "Tai Koo": "TAK",
    "Sai Wan Ho": "SWH",
    "Shau Kei Wan": "SKW",
    "Heng Fa Chuen": "HFC",
    "Chai Wan": "CHW",
    "Whampoa": "WHA",
    "Shek Kip Mei": "SKM",
    "Lok Fu": "LOF",
    "Wong Tai Sin": "WTS",
    "Choi Hung": "CHH",
    "Kowloon Bay": "KOB",
    "Ngau Tau Kok": "NTK",
    "Kwun Tong": "KWT",
    "Lam Tin": "LAT",
    "Disneyland Resort": "DIS",
}

CODE_TO_NAME = {code: name for name, code in NAME_TO_CODE.items()}
BACKGROUND_ASSET_IDS = [
    "newterritories_kowloon",
    "tsingyi",
    "hongkongisland",
    "apleichau",
    "tsingchau",
    "mawan",
    "lantau",
    "airport",
    "lammaisland",
    "cheungchau",
    "heilingchau",
    "sunshineisland",
    "pengchau",
    "shenzhen",
]
NUMBER_PATTERN = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")
PATH_TOKEN_PATTERN = re.compile(r"[A-Za-z]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")


def read_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_station_rows():
    rows = []
    with (MTR_MAP_DIR / "stations.csv").open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = NAME_TO_CODE.get(row["name"])
            if not code:
                continue
            rows.append(
                {
                    "name": row["name"],
                    "code": code,
                    # Use schematic projected coordinates as primary topology coordinates.
                    # This keeps the relative layout used by the classic MTR schematic style.
                    "x": float(row["x_projection"]),
                    "y": float(row["y_projection"]),
                    "x_real": float(row["x_real"]),
                    "y_real": float(row["y_real"]),
                    "x_projection": float(row["x_projection"]),
                    "y_projection": float(row["y_projection"]),
                    "raw_color": row["color"],
                }
            )
    return rows


def parse_translate(transform_text):
    match = re.search(r"translate\(\s*([-+]?\d*\.?\d+)(?:[ ,]+([-+]?\d*\.?\d+))?", transform_text)
    if not match:
        return None
    tx = float(match.group(1))
    ty = float(match.group(2)) if match.group(2) is not None else 0.0
    return tx, ty


def parse_matrix_translation(transform_text):
    match = re.search(
        r"matrix\(\s*[-+]?\d*\.?\d+\s+[+-]?\d*\.?\d+\s+[+-]?\d*\.?\d+\s+[+-]?\d*\.?\d+\s+([-+]?\d*\.?\d+)\s+([-+]?\d*\.?\d+)\s*\)",
        transform_text,
    )
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def read_station_rows_from_svg():
    svg_path = MTR_MAP_DIR / "Hong_Kong_Railway_Route_Map_en.svg"
    if not svg_path.exists():
        return []
    namespace = {
        "svg": "http://www.w3.org/2000/svg",
        "xlink": "http://www.w3.org/1999/xlink",
    }
    root = ET.parse(svg_path).getroot()

    marker_points = []
    for node in root.iter():
        if node.tag.endswith("g") and node.get("id") == "stname":
            break
        if not node.tag.endswith("use"):
            continue
        href = node.get("{http://www.w3.org/1999/xlink}href") or node.get("href")
        if href not in {"#station", "#interchange"}:
            continue
        x_attr = node.get("x")
        y_attr = node.get("y")
        transform_text = node.get("transform") or ""
        if x_attr is not None and y_attr is not None:
            x = float(x_attr)
            y = float(y_attr)
            translate = parse_translate(transform_text)
            if translate:
                x += translate[0]
                y += translate[1]
        else:
            matrix_translation = parse_matrix_translation(transform_text)
            if not matrix_translation:
                continue
            x, y = matrix_translation
        marker_points.append((x, y))

    label_points = []
    for text_node in root.findall(".//svg:text", namespace):
        if text_node.get("systemLanguage"):
            continue
        text_content = " ".join(" ".join(text_node.itertext()).split())
        if not text_content:
            continue
        normalized_name = text_content.replace("–", "-")
        code = NAME_TO_CODE.get(normalized_name)
        if not code:
            continue
        x_attr = text_node.get("x")
        y_attr = text_node.get("y")
        transform_text = text_node.get("transform") or ""
        if x_attr is not None and y_attr is not None:
            x = float(x_attr)
            y = float(y_attr)
        else:
            translate = parse_translate(transform_text)
            if not translate:
                continue
            x, y = translate
        label_points.append((code, normalized_name, x, y))

    if not marker_points or not label_points:
        return []

    snap_distance = 55.0
    marker_candidates = []
    for idx, (_code, _station_name, label_x, label_y) in enumerate(label_points):
        nearest_index = min(
            range(len(marker_points)),
            key=lambda marker_idx: (marker_points[marker_idx][0] - label_x) ** 2 + (marker_points[marker_idx][1] - label_y) ** 2,
        )
        marker_x, marker_y = marker_points[nearest_index]
        distance = ((marker_x - label_x) ** 2 + (marker_y - label_y) ** 2) ** 0.5
        marker_candidates.append((idx, nearest_index, distance))

    marker_candidates.sort(key=lambda item: item[2])
    assigned_markers = {}
    used_markers = set()
    for label_idx, marker_idx, distance in marker_candidates:
        if distance > snap_distance:
            continue
        if marker_idx in used_markers:
            continue
        assigned_markers[label_idx] = marker_idx
        used_markers.add(marker_idx)

    rows = []
    for idx, (code, station_name, _label_x, _label_y) in enumerate(label_points):
        matched_idx = assigned_markers.get(idx)
        if matched_idx is None:
            station_x, station_y = _label_x, _label_y
            source = "label"
        else:
            station_x, station_y = marker_points[matched_idx]
            source = "marker"
        rows.append(
            {
                "name": station_name,
                "code": code,
                "x": station_x,
                "y": station_y,
                "x_real": station_x,
                "y_real": station_y,
                "x_projection": station_x,
                "y_projection": station_y,
                "raw_color": "svg-station",
                "source": source,
            }
        )

    return rows


def read_line_paths():
    svg_path = MTR_MAP_DIR / "Hong_Kong_Railway_Route_Map_en.svg"
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    root = ET.parse(svg_path).getroot()
    path_rows = {}
    for node in root.findall(".//svg:path", namespace):
        asset_name = node.get("id")
        if not asset_name:
            continue
        path_data = node.get("d")
        if not path_data:
            continue
        stroke_width_raw = node.get("stroke-width")
        try:
            stroke_width = float(stroke_width_raw) if stroke_width_raw else 4.0
        except ValueError:
            stroke_width = 4.0
        path_rows[asset_name] = {
            "name": asset_name,
            "class_name": node.get("class", ""),
            "stroke_width": stroke_width,
            "color": node.get("stroke") or "#666666",
            "path": path_data,
        }
    return path_rows


def read_svg_viewbox():
    svg_path = MTR_MAP_DIR / "Hong_Kong_Railway_Route_Map_en.svg"
    if not svg_path.exists():
        return None
    root = ET.parse(svg_path).getroot()
    viewbox = root.get("viewBox")
    if not viewbox:
        return None
    parts = [float(part) for part in viewbox.strip().split()]
    if len(parts) != 4:
        return None
    return {
        "minX": parts[0],
        "minY": parts[1],
        "width": parts[2],
        "height": parts[3],
    }


def get_bounds_from_values(values):
    if not values:
        return None
    return {
        "min": min(values),
        "max": max(values),
        "size": max(values) - min(values),
    }


def get_path_bounds(path_rows, asset_names):
    x_values = []
    y_values = []
    for asset_name in asset_names:
        path_data = path_rows.get(asset_name, {}).get("path")
        if not path_data:
            continue
        points = extract_path_points(path_data)
        for x_val, y_val in points:
            x_values.append(x_val)
            y_values.append(y_val)

    x_bounds = get_bounds_from_values(x_values)
    y_bounds = get_bounds_from_values(y_values)
    if not x_bounds or not y_bounds or x_bounds["size"] == 0 or y_bounds["size"] == 0:
        return None
    return {
        "minX": x_bounds["min"],
        "maxX": x_bounds["max"],
        "width": x_bounds["size"],
        "minY": y_bounds["min"],
        "maxY": y_bounds["max"],
        "height": y_bounds["size"],
    }


def rescale_station_rows_to_paths(station_rows, path_rows, lines_stations):
    asset_names = []
    for line_code in lines_stations.keys():
        asset_names.extend(LINE_META[line_code]["assets"])
    path_bounds = get_path_bounds(path_rows, asset_names)
    if not path_bounds:
        return

    station_x_bounds = get_bounds_from_values([row["x"] for row in station_rows])
    station_y_bounds = get_bounds_from_values([row["y"] for row in station_rows])
    if not station_x_bounds or not station_y_bounds or station_x_bounds["size"] == 0 or station_y_bounds["size"] == 0:
        return

    sx = path_bounds["width"] / station_x_bounds["size"]
    sy = path_bounds["height"] / station_y_bounds["size"]
    tx = path_bounds["minX"] - station_x_bounds["min"] * sx
    ty = path_bounds["minY"] - station_y_bounds["min"] * sy

    for row in station_rows:
        row["x"] = row["x"] * sx + tx
        row["y"] = row["y"] * sy + ty
        row["x_projection"] = row["x"]
        row["y_projection"] = row["y"]


def extract_path_points(path_data):
    if not path_data:
        return []
    points = []
    tokens = PATH_TOKEN_PATTERN.findall(path_data)
    index = 0
    command = None
    current_x = 0.0
    current_y = 0.0
    start_x = 0.0
    start_y = 0.0

    def is_command(token):
        return len(token) == 1 and token.isalpha()

    def read_number():
        nonlocal index
        if index >= len(tokens):
            return None
        token = tokens[index]
        if is_command(token):
            return None
        index += 1
        return float(token)

    while index < len(tokens):
        token = tokens[index]
        if is_command(token):
            command = token
            index += 1
        elif command is None:
            break

        if command in {"M", "m"}:
            first_pair = True
            while True:
                x_val = read_number()
                y_val = read_number()
                if x_val is None or y_val is None:
                    break
                if command == "m":
                    current_x += x_val
                    current_y += y_val
                else:
                    current_x = x_val
                    current_y = y_val
                if first_pair:
                    start_x, start_y = current_x, current_y
                    first_pair = False
                points.append((current_x, current_y))
                if index >= len(tokens) or is_command(tokens[index]):
                    break
            continue

        if command in {"L", "l"}:
            while True:
                x_val = read_number()
                y_val = read_number()
                if x_val is None or y_val is None:
                    break
                if command == "l":
                    current_x += x_val
                    current_y += y_val
                else:
                    current_x = x_val
                    current_y = y_val
                points.append((current_x, current_y))
                if index >= len(tokens) or is_command(tokens[index]):
                    break
            continue

        if command in {"H", "h"}:
            while True:
                x_val = read_number()
                if x_val is None:
                    break
                if command == "h":
                    current_x += x_val
                else:
                    current_x = x_val
                points.append((current_x, current_y))
                if index >= len(tokens) or is_command(tokens[index]):
                    break
            continue

        if command in {"V", "v"}:
            while True:
                y_val = read_number()
                if y_val is None:
                    break
                if command == "v":
                    current_y += y_val
                else:
                    current_y = y_val
                points.append((current_x, current_y))
                if index >= len(tokens) or is_command(tokens[index]):
                    break
            continue

        if command in {"C", "c"}:
            while True:
                values = [read_number() for _ in range(6)]
                if any(value is None for value in values):
                    break
                end_x = values[4]
                end_y = values[5]
                if command == "c":
                    current_x += end_x
                    current_y += end_y
                else:
                    current_x = end_x
                    current_y = end_y
                points.append((current_x, current_y))
                if index >= len(tokens) or is_command(tokens[index]):
                    break
            continue

        if command in {"S", "s", "Q", "q"}:
            while True:
                values = [read_number() for _ in range(4)]
                if any(value is None for value in values):
                    break
                end_x = values[2]
                end_y = values[3]
                if command in {"s", "q"}:
                    current_x += end_x
                    current_y += end_y
                else:
                    current_x = end_x
                    current_y = end_y
                points.append((current_x, current_y))
                if index >= len(tokens) or is_command(tokens[index]):
                    break
            continue

        if command in {"T", "t"}:
            while True:
                x_val = read_number()
                y_val = read_number()
                if x_val is None or y_val is None:
                    break
                if command == "t":
                    current_x += x_val
                    current_y += y_val
                else:
                    current_x = x_val
                    current_y = y_val
                points.append((current_x, current_y))
                if index >= len(tokens) or is_command(tokens[index]):
                    break
            continue

        if command in {"A", "a"}:
            while True:
                values = [read_number() for _ in range(7)]
                if any(value is None for value in values):
                    break
                end_x = values[5]
                end_y = values[6]
                if command == "a":
                    current_x += end_x
                    current_y += end_y
                else:
                    current_x = end_x
                    current_y = end_y
                points.append((current_x, current_y))
                if index >= len(tokens) or is_command(tokens[index]):
                    break
            continue

        if command in {"Z", "z"}:
            current_x = start_x
            current_y = start_y
            points.append((current_x, current_y))
            continue

        # Unknown command, advance to prevent infinite loops.
        if index < len(tokens) and not is_command(tokens[index]):
            index += 1
    return points


def snap_label_station_rows_to_line_paths(station_rows, path_rows, lines_stations):
    code_to_assets = defaultdict(set)
    for line_code, station_codes in lines_stations.items():
        assets = LINE_META.get(line_code, {}).get("assets", [])
        for station_code in station_codes:
            for asset_name in assets:
                code_to_assets[station_code].add(asset_name)

    asset_points_cache = {}
    snap_threshold = 140.0
    for row in station_rows:
        if row.get("source") != "label":
            continue
        points = []
        for asset_name in code_to_assets.get(row["code"], set()):
            if asset_name not in asset_points_cache:
                asset_points_cache[asset_name] = extract_path_points(path_rows.get(asset_name, {}).get("path", ""))
            points.extend(asset_points_cache[asset_name])
        if not points:
            continue

        x = row["x"]
        y = row["y"]
        nearest_x, nearest_y = min(points, key=lambda point: (point[0] - x) ** 2 + (point[1] - y) ** 2)
        distance = ((nearest_x - x) ** 2 + (nearest_y - y) ** 2) ** 0.5
        if distance > snap_threshold:
            continue
        row["x"] = nearest_x
        row["y"] = nearest_y
        row["x_real"] = nearest_x
        row["y_real"] = nearest_y
        row["x_projection"] = nearest_x
        row["y_projection"] = nearest_y
        row["source"] = "label-snapped"


def set_row_coords(row, x_val, y_val, source_tag):
    row["x"] = x_val
    row["y"] = y_val
    row["x_real"] = x_val
    row["y_real"] = y_val
    row["x_projection"] = x_val
    row["y_projection"] = y_val
    row["source"] = source_tag


def apply_branch_terminal_station_overrides(station_rows, path_rows):
    rows_by_code = {row["code"]: row for row in station_rows}

    disney_points = extract_path_points(path_rows.get("disneyline", {}).get("path", ""))
    if disney_points and "SUN" in rows_by_code and "DIS" in rows_by_code:
        sun_row = rows_by_code["SUN"]
        dis_row = rows_by_code["DIS"]
        dis_x, dis_y = max(disney_points, key=lambda point: (point[0] - sun_row["x"]) ** 2 + (point[1] - sun_row["y"]) ** 2)
        set_row_coords(dis_row, dis_x, dis_y, "branch-terminal")

    lhp_points = extract_path_points(path_rows.get("lohasparkspur", {}).get("path", ""))
    if lhp_points and "TKO" in rows_by_code and "LHP" in rows_by_code:
        tko_row = rows_by_code["TKO"]
        lhp_row = rows_by_code["LHP"]
        lhp_x, lhp_y = max(lhp_points, key=lambda point: (point[0] - tko_row["x"]) ** 2 + (point[1] - tko_row["y"]) ** 2)
        set_row_coords(lhp_row, lhp_x, lhp_y, "branch-terminal")


def read_background_paths_from_svg():
    svg_path = MTR_MAP_DIR / "Hong_Kong_Railway_Route_Map_en.svg"
    if not svg_path.exists():
        return []

    namespace = {"svg": "http://www.w3.org/2000/svg"}
    root = ET.parse(svg_path).getroot()
    background = []
    for asset_id in BACKGROUND_ASSET_IDS:
        node = root.find(f".//svg:path[@id='{asset_id}']", namespace)
        if node is None:
            continue
        path_data = node.get("d")
        if not path_data:
            continue
        background.append(
            {
                "asset": asset_id,
                "path": path_data,
                "fill": "#f4ecc8" if asset_id == "shenzhen" else "#eaebed",
                "opacity": 0.58 if asset_id == "shenzhen" else 0.34,
                "class_name": "background-shape",
            }
        )
    return background


def average_position(rows):
    return {
        "x": sum(row["x"] for row in rows) / len(rows),
        "y": sum(row["y"] for row in rows) / len(rows),
        "x_real": sum(row["x_real"] for row in rows) / len(rows),
        "y_real": sum(row["y_real"] for row in rows) / len(rows),
    }


def synthesize_missing_station_rows(lines_stations, candidates_by_code):
    for line_code, station_codes in lines_stations.items():
        for idx, code in enumerate(station_codes):
            if candidates_by_code.get(code):
                continue

            prev_idx = idx - 1
            next_idx = idx + 1

            while prev_idx >= 0 and not candidates_by_code.get(station_codes[prev_idx]):
                prev_idx -= 1
            while next_idx < len(station_codes) and not candidates_by_code.get(station_codes[next_idx]):
                next_idx += 1

            prev_rows = candidates_by_code.get(station_codes[prev_idx], []) if prev_idx >= 0 else []
            next_rows = candidates_by_code.get(station_codes[next_idx], []) if next_idx < len(station_codes) else []

            if prev_rows and next_rows:
                prev_pos = average_position(prev_rows)
                next_pos = average_position(next_rows)
                total_steps = next_idx - prev_idx
                step = idx - prev_idx
                ratio = step / total_steps
                synthetic = {
                    "name": CODE_TO_NAME.get(code, code),
                    "code": code,
                    "x": prev_pos["x"] + (next_pos["x"] - prev_pos["x"]) * ratio,
                    "y": prev_pos["y"] + (next_pos["y"] - prev_pos["y"]) * ratio,
                    "x_real": prev_pos["x_real"] + (next_pos["x_real"] - prev_pos["x_real"]) * ratio,
                    "y_real": prev_pos["y_real"] + (next_pos["y_real"] - prev_pos["y_real"]) * ratio,
                    "raw_color": f"synthetic-{line_code}",
                }
            elif prev_rows:
                prev_pos = average_position(prev_rows)
                synthetic = {
                    "name": CODE_TO_NAME.get(code, code),
                    "code": code,
                    "x": prev_pos["x"] + 40,
                    "y": prev_pos["y"],
                    "x_real": prev_pos["x_real"] + 40,
                    "y_real": prev_pos["y_real"],
                    "raw_color": f"synthetic-{line_code}",
                }
            elif next_rows:
                next_pos = average_position(next_rows)
                synthetic = {
                    "name": CODE_TO_NAME.get(code, code),
                    "code": code,
                    "x": next_pos["x"] - 40,
                    "y": next_pos["y"],
                    "x_real": next_pos["x_real"] - 40,
                    "y_real": next_pos["y_real"],
                    "raw_color": f"synthetic-{line_code}",
                }
            else:
                continue

            candidates_by_code[code].append(synthetic)


def pick_line_nodes(line_code, station_codes, candidates_by_code):
    nodes = []
    for idx, code in enumerate(station_codes):
        candidates = candidates_by_code[code]
        if len(candidates) == 1:
            nodes.append(candidates[0])
            continue

        prev_rows = candidates_by_code.get(station_codes[idx - 1], []) if idx > 0 else []
        next_rows = candidates_by_code.get(station_codes[idx + 1], []) if idx + 1 < len(station_codes) else []

        def distance_score(candidate):
            score = 0.0
            if prev_rows:
                score += min(
                    abs(candidate["x"] - prev_row["x"]) + abs(candidate["y"] - prev_row["y"])
                    for prev_row in prev_rows
                )
            if next_rows:
                score += min(
                    abs(candidate["x"] - next_row["x"]) + abs(candidate["y"] - next_row["y"])
                    for next_row in next_rows
                )
            return score

        chosen = min(candidates, key=distance_score)
        nodes.append(chosen)
    return nodes


def build_topology():
    config = read_config()
    lines_stations = config["mtr_lines_stations"]
    line_paths = read_line_paths()
    svg_viewbox = read_svg_viewbox()
    station_rows = read_station_rows_from_svg()
    fallback_station_rows = read_station_rows()
    rescale_station_rows_to_paths(fallback_station_rows, line_paths, lines_stations)
    if station_rows:
        existing_codes = {row["code"] for row in station_rows}
        for row in fallback_station_rows:
            if row["code"] not in existing_codes:
                station_rows.append(row)
                existing_codes.add(row["code"])
    else:
        station_rows = fallback_station_rows
    snap_label_station_rows_to_line_paths(station_rows, line_paths, lines_stations)
    apply_branch_terminal_station_overrides(station_rows, line_paths)

    candidates_by_code = defaultdict(list)
    for row in station_rows:
        candidates_by_code[row["code"]].append(row)

    synthesize_missing_station_rows(lines_stations, candidates_by_code)

    station_to_lines = defaultdict(list)
    for line_code, station_codes in lines_stations.items():
        for code in station_codes:
            station_to_lines[code].append(line_code)

    stations = []
    line_station_nodes = []
    line_paths_payload = []
    background_paths = read_background_paths_from_svg()
    segments = []
    station_position_lookup = {}

    for code, lines in station_to_lines.items():
        rows = candidates_by_code[code]
        pos = average_position(rows)
        stations.append(
            {
                "code": code,
                "name": CODE_TO_NAME.get(code, code),
                "x": round(pos["x"], 3),
                "y": round(pos["y"], 3),
                "x_real": round(pos["x_real"], 3),
                "y_real": round(pos["y_real"], 3),
                "lines": sorted(lines),
                "is_interchange": len(lines) > 1,
            }
        )
        station_position_lookup[code] = pos

    for line_code, station_codes in lines_stations.items():
        meta = LINE_META[line_code]
        chosen_nodes = pick_line_nodes(line_code, station_codes, candidates_by_code)

        for asset_name in meta["assets"]:
            path_row = line_paths.get(asset_name)
            if not path_row:
                continue

            line_paths_payload.append(
                {
                    "line": line_code,
                    "name": meta["name"],
                    "asset": asset_name,
                    "color": meta["color"],
                    "stroke_width": path_row["stroke_width"],
                    "path": path_row["path"],
                    "class_name": path_row["class_name"],
                }
            )

        for code, node in zip(station_codes, chosen_nodes):
            line_station_nodes.append(
                {
                    "id": f"{line_code}-{code}",
                    "line": line_code,
                    "station_code": code,
                    "station_name": CODE_TO_NAME.get(code, code),
                    "x": round(node["x"], 3),
                    "y": round(node["y"], 3),
                    "x_real": round(node["x_real"], 3),
                    "y_real": round(node["y_real"], 3),
                    "color": meta["color"],
                    "is_interchange": len(station_to_lines[code]) > 1,
                    "transfer_lines": sorted(station_to_lines[code]),
                }
            )

        for from_code, to_code in zip(station_codes, station_codes[1:]):
            from_pos = station_position_lookup[from_code]
            to_pos = station_position_lookup[to_code]
            segments.append(
                {
                    "id": f"{line_code}-{from_code}-{to_code}",
                    "line": line_code,
                    "from_station": from_code,
                    "to_station": to_code,
                    "from_name": CODE_TO_NAME.get(from_code, from_code),
                    "to_name": CODE_TO_NAME.get(to_code, to_code),
                    "x1": round(from_pos["x"], 3),
                    "y1": round(from_pos["y"], 3),
                    "x2": round(to_pos["x"], 3),
                    "y2": round(to_pos["y"], 3),
                }
            )

    if svg_viewbox:
        viewbox_payload = {
            "minX": round(svg_viewbox["minX"], 3),
            "minY": round(svg_viewbox["minY"], 3),
            "width": round(svg_viewbox["width"], 3),
            "height": round(svg_viewbox["height"], 3),
        }
    else:
        max_x = max(node["x"] for node in line_station_nodes)
        max_y = max(node["y"] for node in line_station_nodes)
        min_x = min(node["x"] for node in line_station_nodes)
        min_y = min(node["y"] for node in line_station_nodes)
        padding = 120
        viewbox_payload = {
            "minX": round(min_x - padding, 3),
            "minY": round(min_y - padding, 3),
            "width": round((max_x - min_x) + padding * 2, 3),
            "height": round((max_y - min_y) + padding * 2, 3),
        }

    return {
        "meta": {
            "source": "Hong_Kong_Railway_Route_Map_en.svg + stations.csv",
            "viewBox": viewbox_payload,
        },
        "lines": [
            {
                "code": code,
                "name": meta["name"],
                "color": meta["color"],
                "stations": lines_stations[code],
                "assets": meta["assets"],
            }
            for code, meta in LINE_META.items()
        ],
        "paths": line_paths_payload,
        "background_paths": background_paths,
        "stations": sorted(stations, key=lambda item: item["code"]),
        "line_station_nodes": line_station_nodes,
        "segments": segments,
    }


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    topology = build_topology()
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(topology, f, ensure_ascii=False, indent=2)
    print(f"Wrote topology to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
