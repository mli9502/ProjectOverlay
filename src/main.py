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
META_FPS = 0

def init_worker(df, w, h, fps):
    """
    Initializer for worker processes to share data.
    """
    global DF_GLOBAL, META_W, META_H, META_FPS
    DF_GLOBAL = df
    META_W = w
    META_H = h
    META_FPS = fps

def render_chunk(args):
    """
    Renders an overlay chunk with proper Alpha transparency and composites it.
    args: (start_time, end_time, index)
    """
    start_time, end_time, idx = args
    duration = end_time - start_time
    
    # Files
    overlay_temp = f"temp_overlay_{idx:03d}.mov"
    final_chunk = f"temp_chunk_{idx:03d}.mp4"
    
    # 1. Generate Overlay Only (RGBA)
    def make_frame_overlay(t):
        absolute_t = start_time + t
        time_into_activity = absolute_t + OFFSET_SECONDS
        target_timestamp = DF_GLOBAL.index[0] + pd.Timedelta(seconds=time_into_activity)
        
        try:
            idx_val = DF_GLOBAL.index.get_indexer([target_timestamp], method='nearest')[0]
            row = DF_GLOBAL.iloc[idx_val]
        except Exception:
            row = {}
            row_dict = {}
        else:
            row_dict = row.to_dict() if isinstance(row, pd.Series) else {}
        
        row_dict['full_track_df'] = DF_GLOBAL
        
        # Transparent background (0,0,0,0)
        return create_frame(t, row_dict, META_W, META_H, bg_color=(0, 0, 0, 0))

    overlay_clip = VideoClip(make_frame_overlay, duration=duration)
    
    # Use PNG codec for the overlay video to ensure perfect alpha.
    # We use the EXACT fps of the source video to prevent frame drift/flashing.
    overlay_clip.write_videofile(
        overlay_temp, 
        fps=META_FPS, 
        codec='png',
        audio=False,
        logger=None,
        threads=2
    )
    
    # 2. Composite using FFmpeg with Alpha Overlay
    # ACCURATE SEEKING: put -ss AFTER -i for the source video.
    # We also force the output framerate and set pixel format explicitly.
    cmd = [
        "/usr/bin/ffmpeg", "-y",
        "-i", VIDEO_PATH,
        "-i", overlay_temp,
        "-ss", f"{start_time:.3f}",
        "-t", f"{duration:.3f}",
        "-filter_complex", 
        f"[1:v]format=rgba,scale={META_W}:{META_H}[ovr];"
        f"[0:v]fps={META_FPS},scale={META_W}:{META_H}[base];"
        f"[base][ovr]overlay=0:0[out]",
        "-map", "[out]",
        "-an",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-r", str(META_FPS),
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

def main():
    print("Parsing FIT file...")
    df = parse_fit(FIT_PATH)
    
    print("Reading Video Metadata...")
    w, h, duration, fps = get_video_metadata(VIDEO_PATH)
    print(f"Video: {w}x{h}, {fps:.2f} FPS, Duration: {duration}s")
    
    # Configuration
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
        
    print(f"Starting to render {len(chunks)} chunks with Framerate Sync ({num_processes} workers)...")
    start_gen = time.time()
    
    with multiprocessing.Pool(processes=num_processes, initializer=init_worker, initargs=(df, w, h, fps)) as pool:
        temp_files = pool.map(render_chunk, chunks)
        
    print(f"Parallel generation took {time.time() - start_gen:.1f}s")
    
    # Concatenate Video
    print("Concatenating video chunks...")
    with open("ffmpeg_list.txt", "w") as f:
        for tf in temp_files:
            f.write(f"file '{tf}'\n")
            
    temp_video = "temp_final_no_audio.mp4"
    subprocess.run([
        "/usr/bin/ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "ffmpeg_list.txt", 
        "-c", "copy", temp_video
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Final Step: Add Original Audio
    print("Adding original audio...")
    final_output = "output_final.mp4"
    if os.path.exists(final_output):
        os.remove(final_output)
        
    subprocess.run([
        "/usr/bin/ffmpeg", "-y",
        "-i", temp_video,
        "-i", VIDEO_PATH,
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        final_output
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Cleanup
    for tf in temp_files:
        os.remove(tf)
    os.remove("ffmpeg_list.txt")
    os.remove(temp_video)
    
    print(f"Done! Written {final_output}")

if __name__ == "__main__":
    main()
