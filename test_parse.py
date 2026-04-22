import json
import glob
import os
import pandas as pd

raw_dir = "data/historical/mtr_nexttrain/raw"
files = sorted(glob.glob(os.path.join(raw_dir, "*.json")))
print(f"Found {len(files)} files.")

has_delay = False
data_rows = []

for f in files:
    with open(f, 'r') as fp:
        try:
            d = json.load(fp)
        except:
            continue
        ts = d.get('collected_at')
        for line, stas in d.get('data', {}).items():
            for sta, info in stas.items():
                isdelay = info.get('isdelay', 'N')
                if isdelay == 'Y':
                    has_delay = True
                
                # Extract ttnt
                up_ttnt_1 = None
                down_ttnt_1 = None
                
                try:
                    up_list = info.get('data', {}).get(f"{line}-{sta}", {}).get('UP', [])
                    if up_list:
                        up_ttnt_1 = float(up_list[0].get('ttnt', 0))
                except:
                    pass
                    
                try:
                    down_list = info.get('data', {}).get(f"{line}-{sta}", {}).get('DOWN', [])
                    if down_list:
                        down_ttnt_1 = float(down_list[0].get('ttnt', 0))
                except:
                    pass
                    
                data_rows.append({
                    'timestamp': ts,
                    'line': line,
                    'sta': sta,
                    'isdelay': 1 if isdelay == 'Y' else 0,
                    'up_ttnt_1': up_ttnt_1,
                    'down_ttnt_1': down_ttnt_1
                })

df = pd.DataFrame(data_rows)
print(f"Total rows: {len(df)}")
print(f"Has delay: {has_delay}")
print(df.head())
