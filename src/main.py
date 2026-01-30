import os
# Use system ffmpeg
os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

from moviepy import VideoFileClip, VideoClip, CompositeVideoClip
import sys
import pandas as pd
from datetime import datetime
import numpy as np
import multiprocessing
import subprocess
import time

# Add src to path if running from root
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from extract import parse_fit
from overlay import create_frame

# Global variables for workers
VIDEO_PATH = "DJI_20260128200636_0005_D.MP4"
FIT_PATH = "21697286066_ACTIVITY.fit"
OFFSET_SECONDS = 18
DF_GLOBAL = None

def init_worker(df):
    """
    Initializer for worker processes to share the DataFrame.
    """
    global DF_GLOBAL
    DF_GLOBAL = df

def render_chunk(args):
    """
    Renders a chunk of the video.
    args: (start_time, end_time, index)
    """
    start_time, end_time, idx = args
    output_filename = f"temp_chunk_{idx:03d}.mp4"
    
    # Reload clip inside worker
    clip = VideoFileClip(VIDEO_PATH)
    if end_time > clip.duration:
        end_time = clip.duration
        
    sub_clip = clip.subclipped(start_time, end_time)
    
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
        
        return create_frame(t, row_dict, sub_clip.w, sub_clip.h)

    overlay_clip = VideoClip(make_frame_overlay, duration=sub_clip.duration)
    final_clip = CompositeVideoClip([sub_clip, overlay_clip])
    
    # Render using CPU Encoding (libx264 ultrafast)
    # This avoids GPU session limits and allows high parallelism
    final_clip.write_videofile(
        output_filename, 
        fps=24, 
        codec='libx264',
        preset='ultrafast',   # Fastest encoding
        audio=True,
        threads=2,            # 2 threads per worker for encoding
        logger=None
    )
    return output_filename

def main():
    print("Parsing FIT file...")
    df = parse_fit(FIT_PATH)
    print(f"FIT file range: {df.index.min()} to {df.index.max()}")
    
    clip = VideoFileClip(VIDEO_PATH)
    duration = clip.duration
    
    # Configuration
    # Safe conservative value to prevent system crashes
    # 4 crashed. 1 is safe. Let's try 2.
    num_processes = 2 
    chunk_duration = 20 # seconds
    
    chunks = []
    t = 0
    idx = 0
    while t < duration:
        end = min(t + chunk_duration, duration)
        chunks.append((t, end, idx))
        t = end
        idx += 1
        
    print(f"Starting {len(chunks)} chunks with {num_processes} processes (CPU Encoding)...")
    start_gen = time.time()
    
    with multiprocessing.Pool(processes=num_processes, initializer=init_worker, initargs=(df,)) as pool:
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
