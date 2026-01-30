import os
os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

from moviepy import VideoFileClip, TextClip, CompositeVideoClip, ImageClip
import sys
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

# Add src to path if running from root
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from extract import parse_fit
from overlay import create_frame

def main():
    video_path = "DJI_20260128200636_0005_D.MP4"
    fit_path = "21697286066_ACTIVITY.fit"
    
    # Known timestamps (HARDCODED based on info)
    video_start_time = datetime.fromisoformat("2026-01-29T04:06:37+00:00")
    # Actually fitparse returns local/naive objects usually, or UTC. 
    # Let's rely on relative syncing logic: 
    # Video started at 04:06:37.
    # Activity started at 04:06:19.
    # So Video T=0 corresponds to Activity T = (04:06:37 - 04:06:19) = 18 seconds.
    
    offset_seconds = 18 
    
    print("Parsing FIT file...")
    df = parse_fit(fit_path)
    
    # The dataframe index is Datetime.
    # We need to find the specific row corresponding to video time t.
    # video_time(t) -> real_time = video_start_time + t
    # data lookup -> df.loc[real_time] (nearest)
    
    # Let's verify start time matches what we expect approximately
    print(f"FIT file range: {df.index.min()} to {df.index.max()}")
    
    print("Loading Video...")
    clip = VideoFileClip(video_path)
    # clip = clip.subclipped(0, 10) # For testing
    
    def make_frame_overlay(t):
        # Calculate the relative time in the activity
        # Activity started at T_activity_start
        # Current video frame is at T_video_start + t
        # So we need data at absolute time: T_video_start + t
        
        # However, our dataframe is indexed by timestamps.
        # We can construct the query timestamp.
        
        # WARNING: We need to handle timezone awareness. 
        # df index likely has no timezone if read naively, or UTC.
        # Let's assume the earlier analysis was correct and everything is consistent relative to each other.
        # The safest way is to use the offset from activity start.
        
        # Let's assume df.index[0] is the start of the activity.
        # activity_elapsed = t + offset_seconds
        
        # We can lookup by integer index roughly if we resampled to 1s.
        time_into_activity = t + offset_seconds
        
        # Find the row
        # Since we resampled to 1s, we can just grab integer index? 
        # Or better, use searchsorted or asof
        
        target_timestamp = df.index[0] + pd.Timedelta(seconds=time_into_activity)
        
        # Get nearest row
        try:
            # get_loc with method='nearest' works on datetime index
            idx = df.index.get_indexer([target_timestamp], method='nearest')[0]
            row = df.iloc[idx]
        except Exception:
            # Fallback
            row = {}
        
        # Inject full df for track drawing (inefficient but valid for MVP)
        # Convert to dict-like that has 'full_track_df'
        if isinstance(row, pd.Series):
            row_dict = row.to_dict()
        else:
            row_dict = {}
            
        row_dict['full_track_df'] = df
        
        return create_frame(t, row_dict, clip.w, clip.h)

    from moviepy import VideoClip

    # Create a VideoClip for the overlay
    # We use make_frame which returns WxHxC numpy array (RGB or RGBA)
    # moviepy expects RGB usually, but if we provide RGBA to CompositeVideoClip it might handle transparency?
    # Actually checking docs: ImageClip with transparent mask.
    # Custom VideoClip with make_frame is hardest to do masking with efficiently in moviepy v1 (often slow).
    # But let's try returning RGBA. Moviepy 2.x supports it better.
    
    overlay_clip = VideoClip(make_frame_overlay, duration=clip.duration)
    # overlay_clip = overlay_clip.with_mask(...) if needed, but RGBA usually works in composition if it's the top layer.
    
    final_clip = CompositeVideoClip([clip, overlay_clip])
    
    # Write output
    # Reduce size/duration for testing?
    # User said "I want to build something...". Let's output a short test file first?
    # "Performance: Video processing is slow. We will generate a short 10-second clip first for verification."
    
    # Write output
    output_filename = "output_final.mp4"
    # Use GPU acceleration
    final_clip.write_videofile(
        output_filename, 
        fps=24, 
        codec='h264_nvenc'
    )
    print(f"Written {output_filename}")

if __name__ == "__main__":
    main()
