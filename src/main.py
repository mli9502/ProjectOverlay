import os
os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

from moviepy import VideoFileClip, VideoClip, CompositeVideoClip
import sys
import pandas as pd
from datetime import datetime, timedelta
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
    # Pre-warm local overlay cache inside this process if needed
    # But overlay.py handles its own globals.

def render_chunk(args):
    """
    Renders a chunk of the video.
    args: (start_time, end_time, index)
    """
    start_time, end_time, idx = args
    output_filename = f"temp_chunk_{idx:03d}.mp4"
    
    # Reload clip inside worker
    clip = VideoFileClip(VIDEO_PATH)
    # Create subclip
    # Ensure end_time doesn't exceed duration
    if end_time > clip.duration:
        end_time = clip.duration
        
    sub_clip = clip.subclipped(start_time, end_time)
    
    # Define make_frame using global DF
    def make_frame_overlay(t):
        # t is relative to the start of the subclip?
        # No, in CompositeVideoClip, if we attach it, t is usually relative to the subclip start
        # BUT we need absolute time for data lookup.
        # absolute_t = start_time + t
        
        absolute_t = start_time + t
        time_into_activity = absolute_t + OFFSET_SECONDS
        
        target_timestamp = DF_GLOBAL.index[0] + pd.Timedelta(seconds=time_into_activity)
        
        try:
            # get_loc with method='nearest' works on datetime index
            # searchsorted is faster but requires sorting. DatetimeIndex is sorted.
            # Using get_indexer method='nearest'
            idx = DF_GLOBAL.index.get_indexer([target_timestamp], method='nearest')[0]
            row = DF_GLOBAL.iloc[idx]
        except Exception:
            row = {}
            
        row_dict = row.to_dict() if isinstance(row, pd.Series) else {}
        row_dict['full_track_df'] = DF_GLOBAL
        
        # Note: creates independent image, so thread-safe/process-safe
        return create_frame(t, row_dict, sub_clip.w, sub_clip.h)

    overlay_clip = VideoClip(make_frame_overlay, duration=sub_clip.duration)
    final_clip = CompositeVideoClip([sub_clip, overlay_clip])
    
    # Render
    # Use h264_nvenc if possible
    final_clip.write_videofile(
        output_filename, 
        fps=24, 
        codec='h264_nvenc',
        logger=None # Silence logger to reduce noise
    )
    return output_filename

def main():
    print("Parsing FIT file...")
    df = parse_fit(FIT_PATH)
    print(f"FIT file range: {df.index.min()} to {df.index.max()}")
    
    clip = VideoFileClip(VIDEO_PATH)
    duration = clip.duration
    # FOR TESTING: Limit duration
    # duration = 30 
    
    # Configuration
    num_processes = 8 # or multiprocessing.cpu_count()
    chunk_duration = 20 # seconds per chunk
    
    chunks = []
    t = 0
    idx = 0
    while t < duration:
        end = min(t + chunk_duration, duration)
        chunks.append((t, end, idx))
        t = end
        idx += 1
        
    print(f"Starting {len(chunks)} chunks with {num_processes} processes...")
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
        
    # Standard concat
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
