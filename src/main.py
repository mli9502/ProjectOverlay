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
from overlay import create_frame

# Global variables for workers
VIDEO_PATH = "DJI_20260128200636_0005_D.MP4"
FIT_PATH = "21697286066_ACTIVITY.fit"
OFFSET_SECONDS = 18
DF_GLOBAL = None
META_W = 0
META_H = 0

def init_worker(df, w, h):
    """
    Initializer for worker processes to share data.
    """
    global DF_GLOBAL, META_W, META_H
    DF_GLOBAL = df
    META_W = w
    META_H = h

def render_chunk(args):
    """
    Renders an overlay chunk (transparent) and composites it.
    args: (start_time, end_time, index)
    """
    start_time, end_time, idx = args
    duration = end_time - start_time
    
    # Files
    overlay_temp = f"temp_overlay_{idx:03d}.mov"
    final_chunk = f"temp_chunk_{idx:03d}.mp4"
    
    # 1. Generate Overlay Only (Python Drawing)
    # No source video load!
    
    def make_frame_overlay(t):
        absolute_t = start_time + t
        time_into_activity = absolute_t + OFFSET_SECONDS
        
        target_timestamp = DF_GLOBAL.index[0] + pd.Timedelta(seconds=time_into_activity)
        
        try:
            # get_indexer method='nearest' is fast
            idx = DF_GLOBAL.index.get_indexer([target_timestamp], method='nearest')[0]
            row = DF_GLOBAL.iloc[idx]
        except Exception:
            row = {}
            
        row_dict = row.to_dict() if isinstance(row, pd.Series) else {}
        row_dict['full_track_df'] = DF_GLOBAL
        
        # Draw on blank canvas
        return create_frame(t, row_dict, META_W, META_H)

    # Use 'qtrle' (Animation) codec for alpha support + speed
    overlay_clip = VideoClip(make_frame_overlay, duration=duration)
    
    # We write the overlay to a temp file
    # This is IO bound but much lighter than reading 2.7K source
    overlay_clip.write_videofile(
        overlay_temp, 
        fps=24, 
        codec='qtrle',
        # with_mask not needed if 4-channel array returned and codec supports it
        logger=None,
        threads=2 # Pillow drawing is single threaded mainly, but encoding helps
    )
    
    # 2. Composite using FFmpeg (Hardware accelerated or Fast CPU)
    # ffmpeg -ss start -t dur -i source -i overlay -filter_complex overlay output
    # Note: h264_nvenc might be locked but we can try. 
    # If not, use libx264 ultrafast.
    
    cmd = [
        "/usr/bin/ffmpeg", "-y",
        "-ss", str(start_time),
        "-t", str(duration),
        "-i", VIDEO_PATH,
        "-i", overlay_temp,
        "-filter_complex", "[0:v][1:v]overlay=0:0[out]",
        "-map", "[out]",
        "-map", "0:a", # Copy audio from source
        "-c:v", "libx264", "-preset", "ultrafast", # Use CPU encoding for chunks to avoid GPU lock
        "-c:a", "copy",
        final_chunk
    ]
    
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Cleanup overlay temp immediately
    if os.path.exists(overlay_temp):
        os.remove(overlay_temp)
        
    return final_chunk

def get_video_metadata(path):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-of", "json", path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    w = int(info['streams'][0]['width'])
    h = int(info['streams'][0]['height'])
    dur = float(info['streams'][0]['duration'])
    return w, h, dur

def main():
    print("Parsing FIT file...")
    df = parse_fit(FIT_PATH)
    
    print("Reading Video Metadata...")
    w, h, duration = get_video_metadata(VIDEO_PATH)
    print(f"Video: {w}x{h}, Duration: {duration}s")
    
    # Configuration
    # Since we decoupled memory, we can arguably increase processes!
    # With 2.7K, qtrle writes might be large.
    # Let's try 6 processes.
    num_processes = 6
    chunk_duration = 20 # seconds
    
    chunks = []
    t = 0
    idx = 0
    while t < duration:
        end = min(t + chunk_duration, duration)
        chunks.append((t, end, idx))
        t = end
        idx += 1
        
    print(f"Starting to render {len(chunks)} chunks using Hybrid Pipeline ({num_processes} workers)...")
    start_gen = time.time()
    
    with multiprocessing.Pool(processes=num_processes, initializer=init_worker, initargs=(df, w, h)) as pool:
        temp_files = pool.map(render_chunk, chunks)
        
    print(f"Parallel generation took {time.time() - start_gen:.1f}s")
    
    # Concatenate
    print("Concatenating chunks...")
    with open("ffmpeg_list.txt", "w") as f:
        for tf in temp_files:
            f.write(f"file '{tf}'\n")
            
    final_output = "output_final.mp4"
    if os.path.exists(final_output):
        os.remove(final_output)
        
    subprocess.run([
        "/usr/bin/ffmpeg", "-f", "concat", "-safe", "0", "-i", "ffmpeg_list.txt", 
        "-c", "copy", final_output
    ], check=True)
    
    # Cleanup
    for tf in temp_files:
        os.remove(tf)
    os.remove("ffmpeg_list.txt")
    
    print(f"Done! Written {final_output}")

if __name__ == "__main__":
    main()
