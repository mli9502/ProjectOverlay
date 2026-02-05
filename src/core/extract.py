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
    cols_to_keep = ['speed', 'power', 'cadence', 'altitude', 'grade', 'heart_rate', 'position_lat', 'position_long', 'distance']
    
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

    # Resample to 1s to ensure regular grid
    df = df.resample('1s').mean()
    
    # Handle auto-pause: for dynamic metrics (speed, power, cadence),
    # preserve NaN/zeros during pause instead of interpolating through
    # For position and altitude, forward-fill is appropriate
    
    # Position and altitude: forward-fill (GPS data stays constant when stopped)
    position_cols = ['position_lat', 'position_long', 'altitude', 'distance']
    for col in position_cols:
        if col in df.columns:
            df[col] = df[col].ffill()
    
    # Dynamic metrics: detect paused periods (speed near 0) and don't interpolate
    # First, interpolate only small gaps (< 3s) for these metrics
    # Note: heart_rate is handled separately since HR doesn't go to 0 when stopped
    dynamic_cols = ['speed', 'power', 'cadence']
    for col in dynamic_cols:
        if col in df.columns:
            # Only interpolate gaps of up to 2 seconds (to smooth GPS jitter)
            df[col] = df[col].interpolate(method='time', limit=2)
    
    # Heart rate: fully interpolate since your heart keeps beating during pause
    if 'heart_rate' in df.columns:
        df['heart_rate'] = df['heart_rate'].interpolate(method='time')
    
    # Fill remaining NaNs with 0 (represents stopped/paused state)
    df = df.fillna(0)
    
    # speed often in m/s, convert to km/h and mph
    if 'speed' in df.columns:
        df['speed_kph'] = df['speed'] * 3.6
        df['speed_mph'] = df['speed'] * 2.23694

    # Calculate Gradient if missing or to ensure accuracy
    # Grade = (delta_altitude / delta_distance) * 100
    if 'altitude' in df.columns and 'distance' in df.columns:
        # Calculate diffs
        delta_alt = df['altitude'].diff()
        delta_dist = df['distance'].diff()
        
        # Avoid division by zero and extremely small distances
        # We only calculate grade when moving (dist > 0.5m in 1s)
        mask = delta_dist > 0.5
        
        # Calculate raw grade
        raw_grade = float('nan')
        if len(df) > 0:
            raw_grade = np.full(len(df), np.nan)
            
            # Vectorized calculation
            valid_grade = (delta_alt[mask] / delta_dist[mask]) * 100
            
            # Assign valid grades
            df.loc[mask, 'grade_calculated'] = valid_grade
            
            # Fill NaNs (stopped or invalid) with 0 or previous
            df['grade_calculated'] = df['grade_calculated'].fillna(0)
            
            # Clamp unrealistic values (e.g. GPS jumps)
            df['grade_calculated'] = df['grade_calculated'].clip(-40, 40)
            
            # Smooth the grade (5s rolling window) to reduce GPS noise
            df['grade'] = df['grade_calculated'].rolling(window=5, center=True).mean().fillna(0)
    
    return df
