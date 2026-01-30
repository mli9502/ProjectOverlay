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

def init_worker(df):
    global DF_GLOBAL
    DF_GLOBAL = df

def render_chunk(args):
    """
    Renders a chunk using the stable CompositeVideoClip logic.
    Identical to the single-process version that 'looked great'.
    """
    start_time, end_time, idx = args
    duration = end_time - start_time
    output_filename = f"temp_chunk_{idx:03d}.mp4"
    
    # Reload clip inside worker
    clip = VideoFileClip(VIDEO_PATH).subclipped(start_time, end_time)
    
    # Shared cache for frame and mask
    last_t = -1
    last_img_rgba = None

    def get_rgba_frame(t):
        nonlocal last_t, last_img_rgba
        if t != last_t:
            absolute_t = start_time + t
            time_into_activity = absolute_t + OFFSET_SECONDS
            target_timestamp = DF_GLOBAL.index[0] + pd.Timedelta(seconds=time_into_activity)
            try:
                # Use nearest timestamp
                idx_val = DF_GLOBAL.index.get_indexer([target_timestamp], method='nearest')[0]
                row = DF_GLOBAL.iloc[idx_val]
            except Exception:
                row = {}
            row_dict = row.to_dict() if isinstance(row, pd.Series) else {}
            row_dict['full_track_df'] = DF_GLOBAL
            last_img_rgba = create_frame_rgba(t, row_dict, clip.w, clip.h, bg_color=(0, 0, 0, 0))
            last_t = t
        return last_img_rgba

    def make_frame_rgb(t):
        img = get_rgba_frame(t)
        return np.array(img.convert('RGB'))

    def make_mask(t):
        img = get_rgba_frame(t)
        return np.array(img.split()[-1]) / 255.0

    # Create overlay clip with mask
    overlay_rgb = VideoClip(make_frame_rgb, duration=duration)
    mask_clip = VideoClip(make_mask, duration=duration)
    overlay_clip = overlay_rgb.with_mask(mask_clip)
    
    # Composite
    final_clip = CompositeVideoClip([clip, overlay_clip])
    
    # Write to temp mp4
    # Using codec=libx264 ensures a healthy container that FFmpeg can concat easily.
    final_clip.write_videofile(
        output_filename, 
        fps=clip.fps, # Match source FPS
        codec='libx264',
        preset='ultrafast',
        audio=False, # We'll add audio at the very end to avoid dropouts
        logger=None,
        threads=4 # Smaller threads per worker to avoid OOM
    )
    
    # Close clips to free memory
    clip.close()
    final_clip.close()
    
    return output_filename

def get_video_metadata(path):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,duration,avg_frame_rate", "-of", "json", path]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    stream = json.loads(result.stdout)['streams'][0]
    dur = float(stream['duration'])
    return dur

def main():
    print("Parsing FIT file...")
    df = parse_fit(FIT_PATH)
    duration = get_video_metadata(VIDEO_PATH)
    
    # LIMIT TO 60 SECONDS FOR VERIFICATION
    verification_limit = 60
    if duration > verification_limit:
        print(f"Limiting to first {verification_limit} seconds for verification...")
        duration = verification_limit

    # Configuration
    # 2-3 processes should fit in 8GB RAM for 2.7K video
    num_processes = 2 
    chunk_duration = 20 # seconds
    
    chunks = []
    t = 0; idx = 0
    while t < duration:
        end = min(t + chunk_duration, duration)
        chunks.append((t, end, idx))
        t = end; idx += 1
        
    print(f"Starting parallel rendering of {len(chunks)} chunks ({num_processes} processes)...")
    start_gen = time.time()
    
    with multiprocessing.Pool(processes=num_processes, initializer=init_worker, initargs=(df,)) as pool:
        temp_files = pool.map(render_chunk, chunks)
        
    print(f"Parallel generation took {time.time() - start_gen:.1f}s")
    
    # Concatenate Video
    print("Concatenating video chunks...")
    with open("ffmpeg_list.txt", "w") as f:
        for tf in temp_files: f.write(f"file '{tf}'\n")
            
    temp_video = "temp_final_no_audio.mp4"
    subprocess.run(["/usr/bin/ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "ffmpeg_list.txt", "-c", "copy", temp_video], check=True)
    
    # Merge Audio
    print("Merging continuous audio from source...")
    final_output = "output_final.mp4"
    if os.path.exists(final_output): os.remove(final_output)
    subprocess.run([
        "/usr/bin/ffmpeg", "-y", "-i", temp_video, "-ss", "0", "-t", str(duration), "-i", VIDEO_PATH,
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", final_output
    ], check=True)
    
    # Cleanup
    for tf in temp_files + ["ffmpeg_list.txt", temp_video]:
        if os.path.exists(tf): os.remove(tf)
    
    print(f"Done! Written {final_output}")

if __name__ == "__main__":
    main()
