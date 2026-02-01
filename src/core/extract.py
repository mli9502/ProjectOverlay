import fitparse
import pandas as pd
from datetime import datetime
import numpy as np

def parse_fit(fit_path):
    """
    Parses a FIT file and returns a pandas DataFrame with relevant fitness data.
    The DataFrame is resampled to 1Hz and missing values are interpolated.
    """
    fitfile = fitparse.FitFile(fit_path)
    
    data_list = []
    
    for record in fitfile.get_messages("record"):
        record_data = {}
        for data in record:
            record_data[data.name] = data.value
        
        if "timestamp" in record_data:
            # Map enhanced fields
            if 'enhanced_speed' in record_data:
                record_data['speed'] = record_data['enhanced_speed']
            if 'enhanced_altitude' in record_data:
                record_data['altitude'] = record_data['enhanced_altitude']
            data_list.append(record_data)
            
    df = pd.DataFrame(data_list)
    
    # Ensure timestamp is datetime
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp')
        
    # Select relevant columns
    cols_to_keep = ['speed', 'power', 'cadence', 'altitude', 'grade', 'position_lat', 'position_long', 'distance']
    
    # Filter the dataframe to just these columns existing so far
    existing_cols = [c for c in cols_to_keep if c in df.columns]
    df = df[existing_cols]
    
    # Force convert to numeric, coercing errors
    for col in cols_to_keep:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Convert semicircles to degrees
    if 'position_lat' in df.columns:
        df['position_lat'] = df['position_lat'] * (180 / 2**31)
    if 'position_long' in df.columns:
        df['position_long'] = df['position_long'] * (180 / 2**31)

    # Resample to 1s to ensure regular grid, then interpolate
    df = df.resample('1s').mean()
    df = df.interpolate(method='time')
    
    # Fill remaining NaNs (beginning/end)
    df = df.fillna(0)
    
    # speed often in m/s, convert to km/h and mph
    if 'speed' in df.columns:
        df['speed_kph'] = df['speed'] * 3.6
        df['speed_mph'] = df['speed'] * 2.23694
    
    return df
