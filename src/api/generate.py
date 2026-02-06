"""
Python backend for video generation.
Called from Electron via subprocess.
Reports progress via stdout.
"""
import sys
import os
import json
import argparse
import datetime

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
           "-show_entries", "stream=width,height,duration,avg_frame_rate,bit_rate:format=bit_rate:format_tags=creation_time", 
           "-of", "json", path]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    stream = info['streams'][0]
    w, h, dur = int(stream['width']), int(stream['height']), float(stream['duration'])
    
    # Try to get creation_time
    creation_time_str = info.get('format', {}).get('tags', {}).get('creation_time', None)
    creation_time = None
    if creation_time_str:
        # ISO format: 2026-01-29T04:06:37.000000Z
        try:
             # Handle Z for UTC
            creation_time = datetime.datetime.fromisoformat(creation_time_str.replace('Z', '+00:00'))
        except:
            pass

    fps_parts = stream['avg_frame_rate'].split('/')
    fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else float(fps_parts[0])
    
    # Get bitrate (prefer stream bitrate, fallback to format bitrate)
    bitrate = None
    if 'bit_rate' in stream and stream['bit_rate'] != 'N/A':
        try:
            bitrate = int(stream['bit_rate'])
        except:
            pass
    if bitrate is None and 'format' in info and 'bit_rate' in info['format']:
        try:
            bitrate = int(info['format']['bit_rate'])
        except:
            pass
    
    return w, h, dur, fps, creation_time, bitrate


# Globals for multiprocessing
DF_GLOBAL = None
META_W = 0
META_H = 0
META_FPS = 0
OFFSET_SECONDS = 0
VIDEO_PATH = None
CONFIG = None
LAYOUT_SCALE = 1.0


def init_worker(df, w, h, fps, video_path, config, offset, l_scale):
    global DF_GLOBAL, META_W, META_H, META_FPS, VIDEO_PATH, CONFIG, OFFSET_SECONDS, LAYOUT_SCALE
    DF_GLOBAL = df
    META_W = w
    META_H = h
    META_FPS = fps
    VIDEO_PATH = video_path
    CONFIG = config
    OFFSET_SECONDS = offset
    LAYOUT_SCALE = l_scale


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
            
            # Use calculated layout scale
            scale_factor = LAYOUT_SCALE
            
            last_img_rgba = create_frame_rgba(t, row_dict, META_W, META_H, config=CONFIG, layout_scale=scale_factor)
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
        codec='qtrle',  # QuickTime RLE: lossless RGBA, smaller than PNG
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


def hierarchical_concat(files, output_file, batch_size=10, progress_callback=None):
    """
    Concatenate files in a tree structure to avoid memory issues.
    Instead of concat([f0..f119]) at once, do:
      Round 1: concat f0..f9 -> batch0, f10..f19 -> batch1, ...
      Round 2: concat batch0..batch9 -> super0, ...
      Round 3: ...until one file remains
    """
    round_num = 0
    current_files = files[:]
    all_temp_files = []  # Track all intermediate files for cleanup
    
    while len(current_files) > 1:
        round_num += 1
        next_files = []
        num_batches = (len(current_files) + batch_size - 1) // batch_size
        
        for batch_idx in range(num_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(current_files))
            batch_files = current_files[start:end]
            
            if len(batch_files) == 1:
                # Only one file in this batch, just carry it forward
                next_files.append(batch_files[0])
            else:
                # Concatenate this batch
                batch_output = f"temp_concat_r{round_num}_b{batch_idx}.mov"
                all_temp_files.append(batch_output)
                
                # Write concat list
                list_file = f"temp_concat_r{round_num}_b{batch_idx}.txt"
                all_temp_files.append(list_file)
                with open(list_file, 'w') as f:
                    for bf in batch_files:
                        f.write(f"file '{bf}'\n")
                
                # Run FFmpeg concat
                subprocess.run(
                    ["/usr/bin/ffmpeg", "-y", "-f", "concat", "-safe", "0",
                     "-i", list_file, "-c", "copy", batch_output],
                    check=True, capture_output=True
                )
                next_files.append(batch_output)
                
                if progress_callback:
                    progress_callback(round_num, batch_idx + 1, num_batches)
        
        # Clean up files from previous round (except original input files)
        if round_num > 1:
            for f in current_files:
                if f.startswith('temp_concat_') and os.path.exists(f):
                    os.remove(f)
        
        current_files = next_files
    
    # Rename/move final file to output
    if current_files:
        final_file = current_files[0]
        if final_file != output_file:
            if os.path.exists(output_file):
                os.remove(output_file)
            os.rename(final_file, output_file)
    
    # Clean up remaining temp files (list files, etc.)
    for f in all_temp_files:
        if os.path.exists(f) and f != output_file:
            try:
                os.remove(f)
            except:
                pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fit', required=True, help='Path to FIT file')
    parser.add_argument('--video', required=True, help='Path to video file')
    parser.add_argument('--output', required=True, help='Output path')
    parser.add_argument('--config', type=str, default='{}', help='JSON config')
    parser.add_argument('--quality', type=str, default='crf', help='Quality mode: crf or match')
    args = parser.parse_args()
    
    config = json.loads(args.config)
    
    report_progress(5, "Parsing FIT data...")
    
    df = parse_fit(args.fit)
    w, h, duration, fps, creation_time, source_bitrate = get_video_metadata(args.video)
    
    calculated_offset = 0
    if creation_time and len(df) > 0:
        fit_start = df.index[0]
        # Ensure fit_start is timezone aware (UTC) if not already
        if fit_start.tzinfo is None:
            fit_start = fit_start.replace(tzinfo=datetime.timezone.utc)
            
        calculated_offset = (creation_time - fit_start).total_seconds()
        report_progress(7, f"Auto-Sync: Video created {creation_time}, Activity started {fit_start}, Offset: {calculated_offset:.2f}s")
    else:
        report_progress(7, "Warning: Could not auto-sync (missing metadata). Using default offset 0s")

    report_progress(10, f"Video: {w}x{h}, {duration:.1f}s @ {fps:.1f}fps")

    # Check Quality Mode and modify resolution if needed
    quality_mode = args.quality.lower()
    if quality_mode == 'preview':
        # Force 360p resolution for generation
        w, h = 640, 360
        report_progress(11, "Preview Mode: Overriding resolution to 640x360 for speed.")

    # Calculate layout scale (Reference height: 1080p)
    # If 4K (2160p), scale=2.0. If 360p, scale=0.33.
    layout_scale = h / 1080.0
    
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
        initargs=(df, w, h, fps, args.video, config, calculated_offset, layout_scale)
    ) as pool:
        ovr_files = []
        for i, result in enumerate(pool.imap(render_overlay_chunk, chunks)):
            ovr_files.append(result)
            progress = 15 + int((i + 1) / len(chunks) * 55)
            report_progress(progress, f"Rendering overlay: {i+1}/{len(chunks)} chunks complete")
    
    report_progress(75, "Concatenating overlay chunks...")
    
    # Hierarchical concatenation
    full_ovr = "temp_overlay_full.mov"
    
    def concat_progress(round_num, batch, total):
        # Map to 75-85% progress range
        progress = 75 + int((batch / total) * 10)
        report_progress(progress, f"Concat Round {round_num}: Batch {batch}/{total}")
    
    hierarchical_concat(ovr_files, full_ovr, batch_size=10, progress_callback=concat_progress)
    
    report_progress(85, "Compositing final video...")
    
    # Build encoding options based on quality mode
    quality_mode = args.quality.lower()
    if quality_mode == 'match' and source_bitrate:
        # Match original bitrate
        bitrate_str = f"{source_bitrate // 1000}k"  # Convert to kbps
        encode_opts = ["-c:v", "h264_nvenc", "-preset", "p4", "-b:v", bitrate_str]
        report_progress(86, f"Using 'Match Original' mode: {source_bitrate // 1000000}Mbps")
    elif quality_mode == 'preview':
        # Fast Preview: 360p, libx264 ultrafast (CPU encoding is fast enough at 360p and safer for alignment)
        w, h = 640, 360
        report_progress(11, "Preview Mode: Overriding resolution to 640x360 for speed.")
        # Re-calc layout scale for 360p
        layout_scale = h / 1080.0
        
        encode_opts = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p"]
        report_progress(86, "Using 'Fast Preview' mode (360p CPU/libx264)")
    else:
        # CRF mode (visually lossless)
        encode_opts = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "18", "-b:v", "0"]
        report_progress(86, "Using 'CRF 18' mode (visually lossless)")
    
    # Function to check for overlay_cuda support
    def has_overlay_cuda():
        try:
            result = subprocess.run(["/usr/bin/ffmpeg", "-filters"], capture_output=True, text=True)
            return "overlay_cuda" in result.stdout
        except:
            return False

    use_gpu_overlay = has_overlay_cuda()
    
    # Override for Preview: Use Pure CPU Pipeline
    # Why: 
    # 1. CPU Decoding needed for Rotation fix.
    # 2. CPU Overlay/Encoding avoids Green Bar (NVENC padding/alignment issues).
    # 3. 360p scaling/encoding on CPU is negligible (fast enough).
    if quality_mode == 'preview':
        use_gpu_overlay = False
        report_progress(87, "Preview Mode: Using CPU pipeline for robustness (Rotation/Colors).")

    if use_gpu_overlay:
        report_progress(87, "Using GPU-accelerated overlay (overlay_cuda)")
    
    # Final composite with progress reporting
    # NOTE: We use CPU decoding to ensure rotation metadata is respected (fixing upside-down issues).
    # We then upload to GPU for the heavy overlay work.
    cmd = [
        "/usr/bin/ffmpeg", "-y",
        "-i", args.video,
        "-i", full_ovr,
    ]
    
    if use_gpu_overlay:
        # Hybrid Pipeline: CPU Decode -> GPU Overlay -> GPU Encode
        cmd += [
            "-filter_complex", 
            "[0:v]format=yuv420p,hwupload_cuda,scale_cuda=format=yuv420p[base];[1:v]format=rgba,hwupload_cuda[ovr];[base][ovr]overlay_cuda=0:0[out]",
            "-map", "[out]",
            "-map", "0:a",
        ]
    else:
        # Fallback: CPU overlay
        # For preview, we scale inputs to 640x360
        scale_filter = ",scale=640:360" if quality_mode == 'preview' else ""
        cmd += [
            "-filter_complex", f"[0:v]format=yuv420p{scale_filter}[base];[1:v]format=rgba{scale_filter}[ovr];[base][ovr]overlay=0:0,format=yuv420p[out]",
            "-map", "[out]",
            "-map", "0:a",
        ]
    
    cmd += encode_opts + [
        "-c:a", "aac",
        "-shortest",
        "-progress", "pipe:1",  # Output progress to stdout
        args.output
    ]
    
    # Run with progress parsing
    import re
    # Merge stderr into stdout to prevent buffer deadlock
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    last_progress = 85
    last_update_time = time.time()
    
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        
        # Parse out_time (format: HH:MM:SS.microseconds)
        if line.startswith('out_time='):
            try:
                time_str = line.split('=')[1].strip()
                # Skip N/A or negative values
                if time_str and time_str != 'N/A' and not time_str.startswith('-'):
                    # Parse HH:MM:SS.microseconds
                    parts = time_str.split(':')
                    if len(parts) == 3:
                        hours = int(parts[0])
                        minutes = int(parts[1])
                        seconds = float(parts[2])
                        time_s = hours * 3600 + minutes * 60 + seconds
                        
                        encode_progress = min(94, 85 + int((time_s / duration) * 9))
                        if encode_progress > last_progress or (time.time() - last_update_time > 5):
                            report_progress(encode_progress, f"Encoding: {int(time_s)}s / {int(duration)}s")
                            last_progress = encode_progress
                            last_update_time = time.time()
            except Exception as e:
                pass
        
        # Relay errors to stderr for debugging
        elif "Error" in line or "Fatal" in line or "Failed" in line:
             print(f"FFMPEG: {line}", file=sys.stderr, flush=True)

        # Heartbeat: send update every 10s even if parsing fails
        if time.time() - last_update_time > 10:
            report_progress(last_progress, "Encoding in progress...")
            last_update_time = time.time()
    
    # Check for errors
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd, stderr="See stdout for details")
    
    # Cleanup
    report_progress(95, "Cleaning up temp files...")
    for tf in ovr_files + [full_ovr]:
        if os.path.exists(tf):
            try:
                os.remove(tf)
            except:
                pass
    
    report_progress(100, "Complete!")


if __name__ == '__main__':
    main()
