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
    Renders an overlay chunk with Magenta background and composites it.
    args: (start_time, end_time, index)
    """
    start_time, end_time, idx = args
    duration = end_time - start_time
    
    # Files
    overlay_temp = f"temp_overlay_{idx:03d}.mp4"
    final_chunk = f"temp_chunk_{idx:03d}.mp4"
    
    # 1. Generate Overlay Only (3-Channel RGB with Magenta background)
    def make_frame_overlay(t):
        absolute_t = start_time + t
        time_into_activity = absolute_t + OFFSET_SECONDS
        target_timestamp = DF_GLOBAL.index[0] + pd.Timedelta(seconds=time_into_activity)
        
        try:
            idx = DF_GLOBAL.index.get_indexer([target_timestamp], method='nearest')[0]
            row = DF_GLOBAL.iloc[idx]
        except Exception:
            row = {}
            
        row_dict = row.to_dict() if isinstance(row, pd.Series) else {}
        row_dict['full_track_df'] = DF_GLOBAL
        
        # Use Magenta (255, 0, 255) as Chroma Key background
        # Return as RGB (3 channels) to avoid tiling/stride issues
        return create_frame(t, row_dict, META_W, META_H, bg_color=(255, 0, 255))

    overlay_clip = VideoClip(make_frame_overlay, duration=duration)
    
    # Write overlay as standard high-quality RGB video
    overlay_clip.write_videofile(
        overlay_temp, 
        fps=24, 
        codec='libx264',
        preset='ultrafast',
        audio=False,
        logger=None,
        threads=2
    )
    
    # 2. Composite using FFmpeg with Chroma Key
    # [1:v]colorkey=0xFF00FF:0.01:0.01 -> Makes Magenta transparent
    # Using slow-seek (-i then -ss) for better accuracy on some DJI files
    
    cmd = [
        "/usr/bin/ffmpeg", "-y",
        "-ss", str(start_time),
        "-t", str(duration),
        "-i", VIDEO_PATH,
        "-i", overlay_temp,
        "-filter_complex", "[1:v]colorkey=0xFF00FF:0.05:0.05[ckout];[0:v][ckout]overlay=0:0[out]",
        "-map", "[out]",
        "-map", "0:a?", # Optional audio
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "copy",
        final_chunk
    ]
    
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Cleanup overlay temp
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
    # Safe conservative value: 4 workers. 
    # Since we are not reading source video in workers, memory usage is low.
    num_processes = 4
    chunk_duration = 20 # seconds
    
    chunks = []
    t = 0
    idx = 0
    while t < duration:
        end = min(t + chunk_duration, duration)
        chunks.append((t, end, idx))
        t = end
        idx += 1
        
    print(f"Starting to render {len(chunks)} chunks with Chroma Key Fix ({num_processes} workers)...")
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
