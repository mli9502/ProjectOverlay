import os
os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

from moviepy import VideoClip
import sys
import pandas as pd
import numpy as np
import multiprocessing
import subprocess
import time
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from extract import parse_fit
from overlay import create_frame_rgba

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

def render_overlay_chunk(args):
    """
    Renders overlay using PNG codec (lossless, fast).
    """
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
            last_img_rgba = create_frame_rgba(t, row_dict, META_W, META_H)
            last_t = t
        return last_img_rgba

    def make_frame_rgb(t):
        return np.array(get_rgba_frame(t).convert('RGB'))

    def make_mask(t):
        return np.array(get_rgba_frame(t).split()[-1]) / 255.0

    color_clip = VideoClip(make_frame_rgb, duration=duration)
    mask_clip = VideoClip(make_mask, duration=duration)
    final_clip = color_clip.with_mask(mask_clip)

    # Use PNG codec (lossless alpha, fast)
    final_clip.write_videofile(
        output_filename, 
        fps=META_FPS, 
        codec='png',
        audio=False,
        logger=None
    )
    
    final_clip.close()
    return output_filename

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
    
    # Optimal configuration (verified)
    num_processes = 8
    chunk_duration = 30
    
    chunks = []
    t = 0; idx = 0
    while t < duration:
        end = min(t + chunk_duration, duration)
        chunks.append((t, end, idx))
        t = end; idx += 1
        
    print(f"Step 1: Rendering Overlay Chunks (PNG, large chunks) ({num_processes} processes)...")
    start_gen = time.time()
    with multiprocessing.Pool(processes=num_processes, initializer=init_worker, initargs=(df, w, h, fps)) as pool:
        ovr_files = pool.map(render_overlay_chunk, chunks)
    
    print(f"Overlay rendering took {time.time() - start_gen:.1f}s")
    
    # Concat overlays
    print("Step 2: Concatenating overlays...")
    with open("ovr_list.txt", "w") as f:
        for tf in ovr_files: f.write(f"file '{tf}'\n")
    
    full_ovr = "temp_overlay_full.mov"
    subprocess.run(["/usr/bin/ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "ovr_list.txt", "-c", "copy", full_ovr], check=True, capture_output=True)
    
    # Final composite
    print("Step 3: NVENC GPU Compositing...")
    final_output = "output_final.mp4"
    
    cmd = [
        "/usr/bin/ffmpeg", "-y",
        "-i", VIDEO_PATH,
        "-i", full_ovr,
        "-filter_complex", "[0:v]format=yuv420p[base];[1:v]format=rgba[ovr];[base][ovr]overlay=0:0,format=yuv420p[out]",
        "-map", "[out]",
        "-map", "0:a",
        "-c:v", "h264_nvenc", "-preset", "p1", "-b:v", "20M",
        "-c:a", "aac",
        "-shortest",
        final_output
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    
    # Cleanup
    for tf in ovr_files + ["ovr_list.txt", full_ovr]:
        if os.path.exists(tf): os.remove(tf)
    
    print(f"Done! Total time: {time.time() - start_gen:.1f}s")

if __name__ == "__main__":
    main()
