"""
Python backend for video generation.
Called from Electron via subprocess.
Reports progress via stdout.
"""
import sys
import os
import json
import argparse

# Ensure FFmpeg is found
os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from moviepy import VideoClip
import numpy as np
import pandas as pd
import multiprocessing
import subprocess
import time

from src.core.extract import parse_fit
from src.core.overlay import create_frame_rgba


def get_video_metadata(path):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", 
           "-show_entries", "stream=width,height,duration,avg_frame_rate", 
           "-of", "json", path]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    stream = json.loads(result.stdout)['streams'][0]
    w, h, dur = int(stream['width']), int(stream['height']), float(stream['duration'])
    fps_parts = stream['avg_frame_rate'].split('/')
    fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else float(fps_parts[0])
    return w, h, dur, fps


# Globals for multiprocessing
DF_GLOBAL = None
META_W = 0
META_H = 0
META_FPS = 0
OFFSET_SECONDS = 18
VIDEO_PATH = None
CONFIG = None


def init_worker(df, w, h, fps, video_path, config):
    global DF_GLOBAL, META_W, META_H, META_FPS, VIDEO_PATH, CONFIG
    DF_GLOBAL = df
    META_W = w
    META_H = h
    META_FPS = fps
    VIDEO_PATH = video_path
    CONFIG = config


def render_overlay_chunk(args):
    start_time, end_time, idx = args
    duration = end_time - start_time
    output_filename = f"temp_ovr_{idx:03d}.mov"

    last_t = -1
    last_img_rgba = None

    def get_rgba_frame(t):
        nonlocal last_t, last_img_rgba
        if t != last_t:
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
            last_img_rgba = create_frame_rgba(t, row_dict, META_W, META_H, config=CONFIG)
            last_t = t
        return last_img_rgba

    def make_frame_rgb(t):
        return np.array(get_rgba_frame(t).convert('RGB'))

    def make_mask(t):
        return np.array(get_rgba_frame(t).split()[-1]) / 255.0

    color_clip = VideoClip(make_frame_rgb, duration=duration)
    mask_clip = VideoClip(make_mask, duration=duration)
    final_clip = color_clip.with_mask(mask_clip)

    final_clip.write_videofile(
        output_filename, 
        fps=META_FPS, 
        codec='png',
        audio=False,
        logger=None
    )
    
    final_clip.close()
    return output_filename


def report_progress(percent, status=""):
    """Report progress with percentage and optional status message."""
    if status:
        print(f"STATUS:{status}", flush=True)
    print(f"PROGRESS:{percent}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fit', required=True, help='Path to FIT file')
    parser.add_argument('--video', required=True, help='Path to video file')
    parser.add_argument('--output', required=True, help='Output path')
    parser.add_argument('--config', type=str, default='{}', help='JSON config')
    args = parser.parse_args()
    
    config = json.loads(args.config)
    
    report_progress(5, "Parsing FIT data...")
    
    df = parse_fit(args.fit)
    w, h, duration, fps = get_video_metadata(args.video)
    
    report_progress(10, f"Video: {w}x{h}, {duration:.1f}s @ {fps:.1f}fps")
    
    num_processes = 8
    chunk_duration = 30
    
    chunks = []
    t = 0; idx = 0
    while t < duration:
        end = min(t + chunk_duration, duration)
        chunks.append((t, end, idx))
        t = end; idx += 1
    
    # Render overlay chunks
    report_progress(15, f"Rendering {len(chunks)} overlay chunks...")
    with multiprocessing.Pool(
        processes=num_processes, 
        initializer=init_worker, 
        initargs=(df, w, h, fps, args.video, config)
    ) as pool:
        ovr_files = []
        for i, result in enumerate(pool.imap(render_overlay_chunk, chunks)):
            ovr_files.append(result)
            progress = 15 + int((i + 1) / len(chunks) * 55)
            report_progress(progress, f"Rendered chunk {i+1}/{len(chunks)}")
    
    report_progress(75, "Concatenating overlay chunks...")
    
    # Concat overlays
    with open("ovr_list.txt", "w") as f:
        for tf in ovr_files:
            f.write(f"file '{tf}'\n")
    
    full_ovr = "temp_overlay_full.mov"
    subprocess.run(["/usr/bin/ffmpeg", "-y", "-f", "concat", "-safe", "0", 
                   "-i", "ovr_list.txt", "-c", "copy", full_ovr], 
                  check=True, capture_output=True)
    
    report_progress(85, "Compositing final video...")
    
    # Final composite
    cmd = [
        "/usr/bin/ffmpeg", "-y",
        "-i", args.video,
        "-i", full_ovr,
        "-filter_complex", "[0:v]format=yuv420p[base];[1:v]format=rgba[ovr];[base][ovr]overlay=0:0,format=yuv420p[out]",
        "-map", "[out]",
        "-map", "0:a",
        "-c:v", "h264_nvenc", "-preset", "p1", "-b:v", "20M",
        "-c:a", "aac",
        "-shortest",
        args.output
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    
    # Cleanup
    report_progress(95, "Cleaning up temp files...")
    for tf in ovr_files + ["ovr_list.txt", full_ovr]:
        if os.path.exists(tf):
            os.remove(tf)
    
    report_progress(100, "Complete!")


if __name__ == '__main__':
    main()
