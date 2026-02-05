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
        "-show_entries", "stream=width,height,duration,avg_frame_rate,bit_rate:format=bit_rate:format_tags=creation_time",
        "-of", "json", video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    stream = info['streams'][0]
    
    w = int(stream['width'])
    h = int(stream['height'])
    dur = float(stream['duration'])
    
    # Try to get creation_time from format tags
    creation_time = info.get('format', {}).get('tags', {}).get('creation_time', None)
    
    fps_parts = stream['avg_frame_rate'].split('/')
    if len(fps_parts) == 2:
        fps = float(fps_parts[0]) / float(fps_parts[1])
    else:
        fps = float(fps_parts[0])
    
    # Get bitrate (prefer stream bitrate, fallback to format bitrate)
    bitrate = None
    if 'bit_rate' in stream and stream['bit_rate'] != 'N/A':
        try:
            bitrate = int(stream['bit_rate'])
        except:
            pass
    if bitrate is None and 'format' in info and 'bit_rate' in info['format']:
        try:
            bitrate = int(info['format']['bit_rate'])
        except:
            pass
    
    return {
        'width': w,
        'height': h,
        'duration': dur,
        'fps': fps,
        'creation_time': creation_time,
        'bitrate': bitrate  # in bits per second
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', required=True, help='Path to video file')
    args = parser.parse_args()
    
    metadata = get_video_metadata(args.video)
    print(json.dumps(metadata))


if __name__ == '__main__':
    main()
