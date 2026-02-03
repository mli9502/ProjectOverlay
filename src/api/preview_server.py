"""
Python backend for preview generation.
Called from Electron via subprocess.
Extracts a video frame and composites the overlay on top.
"""
import sys
import os
import json
import base64
import subprocess
import tempfile
from io import BytesIO, StringIO
import argparse
import datetime
import sys
import subprocess
import pandas as pd
from PIL import Image

# Redirect stdout temporarily to suppress overlay.py print statements
_real_stdout = sys.stdout

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Import with suppressed stdout
sys.stdout = StringIO()
from src.core.extract import parse_fit
from src.core.overlay import create_frame_rgba
sys.stdout = _real_stdout


def get_video_frame(video_path, timestamp):
    """Extract a frame from video at the given timestamp using ffmpeg."""
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(timestamp),
            '-i', video_path,
            '-vframes', '1',
            '-update', '1',
            '-f', 'image2',
            tmp_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        
        frame = Image.open(tmp_path).convert('RGBA')
        return frame
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def get_video_creation_time(video_path):
    """Extract creation_time from video metadata."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "format_tags=creation_time",
            "-of", "json", video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        creation_time_str = info.get('format', {}).get('tags', {}).get('creation_time', None)
        
        if creation_time_str:
            # Handle Z for UTC
            return datetime.datetime.fromisoformat(creation_time_str.replace('Z', '+00:00'))
    except Exception as e:
        sys.stderr.write(f"Metadata error: {e}\n")
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fit', required=True, help='Path to FIT file')
    parser.add_argument('--video', required=True, help='Path to video file')
    parser.add_argument('--timestamp', type=int, default=0, help='Timestamp in seconds')
    parser.add_argument('--config', type=str, default='{}', help='JSON config')
    args = parser.parse_args()
    
    # Parse config
    config = json.loads(args.config)
    
    # Suppress stdout during processing
    sys.stdout = StringIO()
    
    try:
        # Parse FIT data
        df = parse_fit(args.fit)
        
        # Calculate offset
        creation_time = get_video_creation_time(args.video)
        offset = 0
        if creation_time and len(df) > 0:
            fit_start = df.index[0]
            if fit_start.tzinfo is None:
                fit_start = fit_start.replace(tzinfo=datetime.timezone.utc)
            offset = (creation_time - fit_start).total_seconds()
            
        # Get data at timestamp + offset
        time_into_activity = args.timestamp + offset
        
        # Find row by time (since index is DatetimeIndex)
        target_time = df.index[0] + pd.Timedelta(seconds=time_into_activity)
        
        try:
            idx_val = df.index.get_indexer([target_time], method='nearest')[0]
            row = df.iloc[idx_val]
        except:
            if len(df) > 0:
                row = df.iloc[0]
            else:
                row = {}
        
        row_dict = row.to_dict()
        row_dict['full_track_df'] = df
        
        # Extract video frame
        video_frame = get_video_frame(args.video, args.timestamp)
        width, height = video_frame.size
        
        # Generate overlay frame at video dimensions
        overlay_frame = create_frame_rgba(args.timestamp, row_dict, width, height, config=config)
        
        # Composite overlay on video frame
        video_frame.paste(overlay_frame, (0, 0), overlay_frame)
        
    finally:
        # Restore stdout
        sys.stdout = _real_stdout
    
    # Encode as base64
    buffer = BytesIO()
    video_frame.save(buffer, format='PNG')
    base64_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    # Output to stdout (only the base64 image)
    print(base64_image)


if __name__ == '__main__':
    main()
