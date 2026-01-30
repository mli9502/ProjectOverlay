import os
# Use system ffmpeg
os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

from moviepy import VideoFileClip, VideoClip
import sys
import pandas as pd
from datetime import datetime
import numpy as np
import multiprocessing
import subprocess
import time
import json

# Add src to path if running from root
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from extract import parse_fit
from overlay import create_frame_rgba

# Global variables for workers
VIDEO_PATH = "DJI_20260128200636_0005_D.MP4"
FIT_PATH = "21697286066_ACTIVITY.fit"
OFFSET_SECONDS = 18
DF_GLOBAL = None
META_W = 0
META_H = 0
META_FPS = 0

def init_worker(df, w, h, fps):
    global DF_GLOBAL, META_W, META_H, META_FPS
    DF_GLOBAL = df
    META_W = w
    META_H = h
    META_FPS = fps

def render_chunk(args):
    start_time, end_time, idx = args
    duration = end_time - start_time
    
    rgb_temp = f"temp_rgb_{idx:03d}.mp4"
    mask_temp = f"temp_mask_{idx:03d}.mp4"
    final_chunk = f"temp_chunk_{idx:03d}.mp4"
    
    def get_rgba_p(t):
        absolute_t = start_time + t
        time_into_activity = absolute_t + OFFSET_SECONDS
        target_timestamp = DF_GLOBAL.index[0] + pd.Timedelta(seconds=time_into_activity)
        try:
            idx_val = DF_GLOBAL.index.get_indexer([target_timestamp], method='nearest')[0]
            row = DF_GLOBAL.iloc[idx_val]
        except:
            row = {}
        row_dict = row.to_dict() if isinstance(row, pd.Series) else {}
        row_dict['full_track_df'] = DF_GLOBAL
        return create_frame_rgba(t, row_dict, META_W, META_H, bg_color=(0, 0, 0, 0))

    def make_rgb(t):
        return np.array(get_rgba_p(t).convert('RGB'))
    
    def make_mask(t):
        return np.array(get_rgba_p(t).split()[-1]) / 255.0

    print(f"Chunk {idx}: Rendering RGB and Mask...")
    rgb_clip = VideoClip(make_rgb, duration=duration)
    rgb_clip.write_videofile(rgb_temp, fps=META_FPS, codec='libx264', preset='ultrafast', audio=False, logger=None)
    
    mask_clip = VideoClip(make_mask, duration=duration)
    mask_clip.write_videofile(mask_temp, fps=META_FPS, codec='libx264', preset='ultrafast', audio=False, logger=None)

    # Composite via FFmpeg - DEBUG VERSION: capture output
    print(f"Chunk {idx}: Compositing...")
    cmd = [
        "/usr/bin/ffmpeg", "-y",
        "-i", VIDEO_PATH, # Move -ss after -i for a test to see if it fixes "black video"
        "-i", rgb_temp,
        "-i", mask_temp,
        "-ss", f"{start_time:.3f}",
        "-t", f"{duration:.3f}",
        "-filter_complex", 
        "[1:v][2:v]alphamerge[ovr];[0:v][ovr]overlay=0:0[out]",
        "-map", "[out]",
        "-an",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-r", str(META_FPS),
        final_chunk
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FFmpeg Error in chunk {idx}: {res.stderr}")
    return final_chunk

def get_video_metadata(path):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,duration,avg_frame_rate", "-of", "json", path]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    stream = json.loads(result.stdout)['streams'][0]
    w, h, dur = int(stream['width']), int(stream['height']), float(stream['duration'])
    fps_parts = stream['avg_frame_rate'].split('/')
    fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else float(fps_parts[0])
    return w, h, dur, fps

def main():
    print("Parsing FIT file...")
    df = parse_fit(FIT_PATH)
    w, h, duration, fps = get_video_metadata(VIDEO_PATH)
    
    # DEBUG: Only 2 seconds, 1 chunk
    num_processes = 1
    duration = 5
    chunk_duration = 5
    
    chunks = [(0, 5, 0)]
        
    print(f"Starting DEBUG hybrid generation...")
    with multiprocessing.Pool(processes=num_processes, initializer=init_worker, initargs=(df, w, h, fps)) as pool:
        temp_files = pool.map(render_chunk, chunks)
    print("Debug render finished. Check temp_chunk_000.mp4 and temp_rgb_000.mp4")

if __name__ == "__main__":
    main()
