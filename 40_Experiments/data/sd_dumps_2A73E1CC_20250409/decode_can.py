import sys
import os
from asammdf import MDF
import pandas as pd

def decode_mf4(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        return

    print(f"Analyzing: {file_path}")
    mdf = MDF(file_path)
    
    # Target IDs
    target_ids = {0x7DF, 0x7E0, 0x7E7, 0x17FC007B, 0x17FE007B}
    
    df = mdf.to_dataframe(time_as_date=False)
    results = []
    
    # Identify columns that contain CAN IDs (exclude IDE)
    id_data_pairs = []
    for col in df.columns:
        if '.ID' in col and '.IDE' not in col:
            data_col = col.replace('.ID', '.DataBytes')
            if data_col in df.columns:
                id_data_pairs.append((col, data_col))
    
    print(f"{'Timestamp':<12} | {'ID':<10} | {'Data (Hex)':<25} | {'Interpretation'}")
    print("-" * 80)

    for _, row in df.iterrows():
        timestamp = row.name
        for id_col, data_col in id_data_pairs:
            can_id = row[id_col]
            if pd.isna(can_id): continue
            
            can_id_int = int(can_id)
            if can_id_int in target_ids:
                data_raw = row[data_col]
                data_hex = data_raw.hex(' ').upper() if isinstance(data_raw, (bytes, bytearray)) else str(data_raw)
                
                # Simple interpretation logic
                note = ""
                if can_id_int == 0x17FC007B:
                    note = "Request to BMS"
                elif can_id_int == 0x17FE007B:
                    note = "Response from BMS"
                    # Decode SOC if Data is 04 62 02 8C XX ...
                    parts = data_hex.split()
                    if len(parts) >= 5 and parts[1] == '62' and parts[2] == '02' and parts[3] == '8C':
                        soc_raw = int(parts[4], 16)
                        soc_pct = soc_raw / 2.5
                        note += f" -> [SOC: {soc_pct:.1f}%]"

                results.append(f"{timestamp:<12.4f} | {hex(can_id_int).upper():<10} | {data_hex:<25} | {note}")

    if not results:
        print("No diagnostic data found yet. Is the car in READY mode?")
    else:
        for r in results:
            print(r)

if __name__ == "__main__":
    # Find the latest MF4 file automatically
    log_dir = r'C:\Users\Nitrox\OneDrive\Desktop\CANedge 09042025\LOG\2A73E1CC'
    subdirs = sorted([d for d in os.listdir(log_dir) if os.path.isdir(os.path.join(log_dir, d))])
    if subdirs:
        latest_dir = os.path.join(log_dir, subdirs[-1])
        files = sorted([f for f in os.listdir(latest_dir) if f.endswith('.MF4')])
        if files:
            latest_file = os.path.join(latest_dir, files[-1])
            decode_mf4(latest_file)
        else:
            print("No MF4 files found.")
    else:
        print("No log directories found.")
