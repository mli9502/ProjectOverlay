"""
Calculate synchronization offset between Video and FIT file.
Called from Electron/Web Server.
Output: JSON { offset: float, video_created: str, fit_start: str }
"""
import sys
import os
import json
import argparse
import datetime
import subprocess

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.core.extract import parse_fit

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
    args = parser.parse_args()
    
    result = {
        'offset': 0,
        'video_created': None,
        'fit_start': None,
        'success': False,
        'message': ''
    }
    
    try:
        # Get Video Time
        creation_time = get_video_creation_time(args.video)
        if not creation_time:
            result['message'] = 'Could not extract creation time from video'
            print(json.dumps(result))
            return

        result['video_created'] = creation_time.isoformat()
        
        # Get FIT Time
        df = parse_fit(args.fit)
        if len(df) == 0:
            result['message'] = 'FIT file empty or invalid'
            print(json.dumps(result))
            return
            
        fit_start = df.index[0]
        if fit_start.tzinfo is None:
            fit_start = fit_start.replace(tzinfo=datetime.timezone.utc)
            
        result['fit_start'] = fit_start.isoformat()
        
        # Calculate
        offset = (creation_time - fit_start).total_seconds()
        result['offset'] = offset
        result['success'] = True
        
    except Exception as e:
        result['message'] = str(e)
        
    print(json.dumps(result))

if __name__ == '__main__':
    main()
