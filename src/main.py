import os
# Use system ffmpeg
os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

from moviepy import VideoFileClip, VideoClip, CompositeVideoClip
import sys
import pandas as pd
from datetime import datetime
import numpy as np
import json

# Add src to path if running from root
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from extract import parse_fit
from overlay import create_frame_rgba

def get_video_metadata(path):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration,avg_frame_rate",
        "-of", "json", path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    stream = info['streams'][0]
    w = int(stream['width'])
    h = int(stream['height'])
    dur = float(stream['duration'])
    
    # Parse fps (e.g. "30000/1001" or "30/1")
    fps_parts = stream['avg_frame_rate'].split('/')
    if len(fps_parts) == 2:
        fps = float(fps_parts[0]) / float(fps_parts[1])
    else:
        fps = float(fps_parts[0])
        
    return w, h, dur, fps

import subprocess

def main():
    video_path = "DJI_20260128200636_0005_D.MP4"
    fit_path = "21697286066_ACTIVITY.fit"
    offset_seconds = 18 
    
    # 1. Load Data
    print("Parsing FIT file...")
    df = parse_fit(fit_path)
    
    # 2. Setup Video
    print("Reading Video Metadata...")
    w, h, duration_meta, fps = get_video_metadata(video_path)
    print(f"Video: {w}x{h}, {fps:.2f} FPS, Duration: {duration_meta}s")
    
    print("Loading Video...")
    clip = VideoFileClip(video_path)
    
    # LIMIT TO 60 SECONDS FOR VERIFICATION
    limit_dur = 60
    if clip.duration > limit_dur:
        print(f"Limiting to first {limit_dur} seconds for verification...")
        clip = clip.subclipped(0, limit_dur)

    # Shared cache
    last_t = -1
    last_img_rgba = None

    def get_rgba_frame(t):
        nonlocal last_t, last_img_rgba
        if t != last_t:
            time_into_activity = t + offset_seconds
            target_timestamp = df.index[0] + pd.Timedelta(seconds=time_into_activity)
            try:
                idx = df.index.get_indexer([target_timestamp], method='nearest')[0]
                row = df.iloc[idx]
            except Exception:
                row = {}
            
            row_dict = row.to_dict() if isinstance(row, pd.Series) else {}
            row_dict['full_track_df'] = df
            
            last_img_rgba = create_frame_rgba(t, row_dict, clip.w, clip.h, bg_color=(0, 0, 0, 0))
            last_t = t
        return last_img_rgba

    def make_frame_rgb(t):
        img = get_rgba_frame(t)
        return np.array(img.convert('RGB'))

    def make_mask(t):
        img = get_rgba_frame(t)
        # MoviePy 2.x masks expect a [0, 1] float array
        return np.array(img.split()[-1]) / 255.0

    # 3. Create Clips
    print("Initializing overlay clips...")
    overlay_rgb = VideoClip(make_frame_rgb, duration=clip.duration)
    # In MoviePy 2, the mask is just set directly if it's a 1-channel clip.
    mask_clip = VideoClip(make_mask, duration=clip.duration)
    overlay_clip = overlay_rgb.with_mask(mask_clip)
    
    # 4. Composite
    final_clip = CompositeVideoClip([clip, overlay_clip])
    
    output_filename = "output_final.mp4"
    print(f"Starting stable generation (60s limit, MoviePy 2.x)...")
    
    start_time = datetime.now()
    final_clip.write_videofile(
        output_filename, 
        fps=fps, 
        codec='libx264',
        preset='ultrafast',
        threads=32
    )
    end_time = datetime.now()
    duration = end_time - start_time
    print(f"Done! Written {output_filename}")
    print(f"Total generation time: {duration}")

if __name__ == "__main__":
    main()
