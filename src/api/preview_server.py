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
        
        # Get data at timestamp
        if args.timestamp < len(df):
            row = df.iloc[args.timestamp]
        else:
            row = df.iloc[-1]
        
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
