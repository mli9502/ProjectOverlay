"""
Get video metadata (duration, dimensions, fps).
Called from Electron via subprocess.
"""
import sys
import os
import json
import subprocess
import argparse


def get_video_metadata(video_path):
    """Get video metadata using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration,avg_frame_rate",
        "-of", "json", video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    stream = info['streams'][0]
    
    w = int(stream['width'])
    h = int(stream['height'])
    dur = float(stream['duration'])
    
    fps_parts = stream['avg_frame_rate'].split('/')
    if len(fps_parts) == 2:
        fps = float(fps_parts[0]) / float(fps_parts[1])
    else:
        fps = float(fps_parts[0])
    
    return {
        'width': w,
        'height': h,
        'duration': dur,
        'fps': fps
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', required=True, help='Path to video file')
    args = parser.parse_args()
    
    metadata = get_video_metadata(args.video)
    print(json.dumps(metadata))


if __name__ == '__main__':
    main()
