import os
import sys
import json
import asyncio
import aiohttp
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from src.utils.config import config

async def fetch_schedule(session: aiohttp.ClientSession, line: str, sta: str, base_url: str):
    url = f"{base_url}?line={line}&sta={sta}"
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                return line, sta, data
            else:
                print(f"HTTP {resp.status} for {line}-{sta}")
                return line, sta, None
    except Exception as e:
        print(f"Error fetching {line}-{sta}: {e}")
        return line, sta, None

async def collect_all_stations():
    base_url = config.get("mtr_api_base_url", "https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php")
    lines_stations = config.get("mtr_lines_stations", {})
    output_dir = os.path.join(project_root, config.get("mtr_raw_data_dir", "data/historical/mtr_nexttrain/raw"))
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {
        "collected_at": timestamp,
        "data": {}
    }
    
    print(f"[{timestamp}] Starting MTR data collection cycle...")
    
    async with aiohttp.ClientSession() as session:
        for line, stations in lines_stations.items():
            for sta in stations:
                l, s, data = await fetch_schedule(session, line, sta, base_url)
                if data:
                    # Log delay events if found
                    if data.get("isdelay") == "Y":
                        print(f"⚠️ Delay detected at {line}-{sta}!")
                    
                    if line not in results["data"]:
                        results["data"][line] = {}
                    results["data"][line][sta] = data
                
                # Rate limiting to avoid 429
                await asyncio.sleep(0.5)
                
    output_file = os.path.join(output_dir, f"mtr_schedule_{timestamp}.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print(f"[{timestamp}] Cycle complete. Data saved to {output_file}")

def main():
    interval = config.get("mtr_logger_interval_seconds", 30)
    print(f"Starting MTR Data Logger. Interval: {interval} seconds.")
    try:
        while True:
            asyncio.run(collect_all_stations())
            print(f"Sleeping for {interval} seconds...")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("MTR Data Logger stopped.")

if __name__ == "__main__":
    main()
