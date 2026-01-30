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
    """
    Renders an overlay chunk (RGB and Alpha) and composites it via FFmpeg.
    """
    start_time, end_time, idx = args
    duration = end_time - start_time
    
    rgb_temp = f"temp_rgb_{idx:03d}.mp4"
    mask_temp = f"temp_mask_{idx:03d}.mp4"
    final_chunk = f"temp_chunk_{idx:03d}.mp4"
    
    # Shared PIL drawing function
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

    # Render RGB Content
    def make_rgb(t):
        return np.array(get_rgba_p(t).convert('RGB'))
    
    # Render Alpha Mask
    def make_mask(t):
        # MoviePy 2.x Mask expects 1-channel [0, 1] float
        return np.array(get_rgba_p(t).split()[-1]) / 255.0

    print(f"Chunk {idx}: Rendering RGB and Mask...")
    rgb_clip = VideoClip(make_rgb, duration=duration)
    rgb_clip.write_videofile(rgb_temp, fps=META_FPS, codec='libx264', preset='ultrafast', audio=False, logger=None)
    
    mask_clip = VideoClip(make_mask, duration=duration)
    mask_clip.write_videofile(mask_temp, fps=META_FPS, codec='libx264', preset='ultrafast', audio=False, logger=None)

    # Composite via FFmpeg
    # Use accurate seeking for the source video
    cmd = [
        "/usr/bin/ffmpeg", "-y",
        "-ss", f"{start_time:.3f}",
        "-t", f"{duration:.3f}",
        "-i", VIDEO_PATH,
        "-i", rgb_temp,
        "-i", mask_temp,
        "-filter_complex", 
        "[1:v][2:v]alphamerge[ovr];[0:v][ovr]overlay=0:0[out]",
        "-map", "[out]",
        "-an",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-r", str(META_FPS),
        final_chunk
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    
    # Cleanup temps
    for f in [rgb_temp, mask_temp]:
        if os.path.exists(f): os.remove(f)
        
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
    print(f"Video: {w}x{h}, {fps:.2f} FPS, Duration: {duration}s")
    
    # Optimized parallelism for decoupled render
    num_processes = 6
    chunk_duration = 30
    
    chunks = []
    t = 0
    idx = 0
    while t < duration:
        end = min(t + chunk_duration, duration)
        chunks.append((t, end, idx))
        t = end; idx += 1
        
    print(f"Starting optimized hybrid generation ({num_processes} processes)...")
    start_gen = time.time()
    with multiprocessing.Pool(processes=num_processes, initializer=init_worker, initargs=(df, w, h, fps)) as pool:
        temp_files = pool.map(render_chunk, chunks)
        
    # Concatenate Video Chunks
    with open("ffmpeg_list.txt", "w") as f:
        for tf in temp_files: f.write(f"file '{tf}'\n")
            
    temp_video = "temp_final_no_audio.mp4"
    subprocess.run(["/usr/bin/ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "ffmpeg_list.txt", "-c", "copy", temp_video], check=True)
    
    # Merge Audio
    print("Merging continuous audio...")
    final_output = "output_final.mp4"
    subprocess.run([
        "/usr/bin/ffmpeg", "-y", "-i", temp_video, "-i", VIDEO_PATH,
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", final_output
    ], check=True)
    
    # Cleanup
    for tf in temp_files + ["ffmpeg_list.txt", temp_video]:
        if os.path.exists(tf): os.remove(tf)
    
    print(f"Generation complete: {time.time() - start_gen:.1f}s")

if __name__ == "__main__":
    main()
