from PIL import Image, ImageDraw, ImageFont
import numpy as np
import pandas as pd


# Load fonts globally
try:
    FONT_LARGE = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
    FONT_LABEL = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
except:
    FONT_LARGE = ImageFont.load_default()
    FONT_LABEL = ImageFont.load_default()

# Map cache globals
CACHED_BACKGROUND = None
MAP_OBJ = None

# Profile cache globals
CACHED_PROFILE = None
PROFILE_W = 0
PROFILE_H = 0


def create_frame_rgba(t, data_row, width, height, bg_color=(0, 0, 0, 0)):
    """
    Creates a transparent PIL image with the HUD overlay for a specific time t.
    """
    # Create a background with bg_color (supports RGBA or RGB)
    img = Image.new('RGBA' if len(bg_color) == 4 else 'RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Fonts are loaded globally


    # Layout configuration
    margin_left = 50
    margin_top = 100
    spacing = 150
    margin_top = 50
    
    # 1. Speed (Top Left)
    speed = data_row.get('speed_mph', 0)
    if pd.isna(speed): speed = 0
    
    draw.text((margin_left, margin_top), f"{speed:.0f}", font=FONT_LARGE, fill="white")
    draw.text((margin_left, margin_top + 80), "MPH", font=FONT_LABEL, fill="white")
    
    # 2. Power
    power = data_row.get('power', 0)
    if pd.isna(power): power = 0
    
    draw.text((margin_left, margin_top + 200), f"{power:.0f}", font=FONT_LARGE, fill="white")
    draw.text((margin_left, margin_top + 300), "W", font=FONT_LABEL, fill="white")
    
    # 3. Cadence
    cadence = data_row.get('cadence', 0)
    if pd.isna(cadence): cadence = 0
    
    draw.text((margin_left, margin_top + 400), f"{cadence:.0f}", font=FONT_LARGE, fill="white")
    draw.text((margin_left, margin_top + 500), "RPM", font=FONT_LABEL, fill="white")
    
    # 4. Gradient
    grade = data_row.get('grade', 0) # Assuming this column exists or was renamed properly
    # If grade is missing or nan, show 0
    if pd.isna(grade):
        grade = 0
    draw.text((margin_left, margin_top + 600), f"{grade:.1f}%", font=FONT_LARGE, fill="white")
    draw.text((margin_left, margin_top + 700), "GRADIENT", font=FONT_LABEL, fill="white")
    
    # 5. Mini Map with Real Background
    full_track = data_row.get('full_track_df')
    if full_track is not None and not full_track.empty:
        # Map settings
        map_size = 300
        map_x = width - map_size - 50
        map_y = 50
        
        # Get bounds
        lats = full_track['position_lat'].dropna()
        longs = full_track['position_long'].dropna()
        
        if not lats.empty and not longs.empty:
            min_lat, max_lat = lats.min(), lats.max()
            min_lon, max_lon = longs.min(), longs.max()
            
            # Add padding to bounds
            lat_pad = (max_lat - min_lat) * 0.1
            lon_pad = (max_lon - min_lon) * 0.1
            if lat_pad == 0: lat_pad = 0.001
            if lon_pad == 0: lon_pad = 0.001
            
            global CACHED_BACKGROUND, MAP_OBJ
            
            # Check for cached background
            if CACHED_BACKGROUND is None:
                import smopy
                try:
                    # 1. Initialize Map
                    if MAP_OBJ is None:
                        MAP_OBJ = smopy.Map(
                            (min_lat - lat_pad, min_lon - lon_pad, 
                             max_lat + lat_pad, max_lon + lon_pad), 
                            z=15
                        )
                        print("Map initialized.")
                    
                    if MAP_OBJ:
                        # 2. Create Base Image (Map + Track)
                        map_img = MAP_OBJ.to_pil()
                        map_img = map_img.resize((map_size, map_size))
                        map_img = map_img.convert("RGBA")
                        
                        # Draw full track on base image
                        map_draw = ImageDraw.Draw(map_img)
                        
                        # Helper for projection (local to this scope for init)
                        def project_point_static(lat, lon):
                            x, y = MAP_OBJ.to_pixels(lat, lon)
                            orig_w, orig_h = MAP_OBJ.img.size if hasattr(MAP_OBJ, 'img') and MAP_OBJ.img else MAP_OBJ.to_pil().size
                            scale_x = map_size / orig_w
                            scale_y = map_size / orig_h
                            return x * scale_x, y * scale_y

                        points = []
                        for i in range(0, len(lats), 5): 
                            points.append(project_point_static(lats.iloc[i], longs.iloc[i]))
                        
                        if len(points) > 1:
                            map_draw.line(points, fill="blue", width=3)
                            
                        CACHED_BACKGROUND = map_img
                    else:
                         CACHED_BACKGROUND = None

                except Exception as e:
                    print(f"Map cache init failed: {e}")
                    CACHED_BACKGROUND = None

            # Use Cached Background
            if CACHED_BACKGROUND and MAP_OBJ:
                # 1. Paste Cached Map
                draw.rectangle((map_x-2, map_y-2, map_x+map_size+2, map_y+map_size+2), outline="white", width=2)
                img.paste(CACHED_BACKGROUND, (map_x, map_y))
                
                # 2. Draw Current Position
                curr_lat = data_row.get('position_lat')
                curr_lon = data_row.get('position_long')
                
                if pd.notna(curr_lat) and pd.notna(curr_lon):
                    x, y = MAP_OBJ.to_pixels(curr_lat, curr_lon)
                    orig_w, orig_h = MAP_OBJ.img.size if hasattr(MAP_OBJ, 'img') and MAP_OBJ.img else MAP_OBJ.to_pil().size
                    scale_x = map_size / orig_w
                    scale_y = map_size / orig_h
                    
                    cx = map_x + x * scale_x
                    cy = map_y + y * scale_y
                    
                    r = 6
                    draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill="yellow", outline="black")
            else:
                # Fallback to old drawing if map failed
                pass 

    # 6. Elevation Profile (Bottom)
    full_track = data_row.get('full_track_df')
    if full_track is not None and not full_track.empty:
        # Profile settings
        prof_h = 150
        prof_w = width - 100
        prof_x = 50
        prof_y = height - prof_h - 50
        
        global CACHED_PROFILE, PROFILE_W, PROFILE_H
        
        dists = full_track['distance'].dropna()
        alts = full_track['altitude'].dropna()
        
        if not dists.empty and not alts.empty:
            min_dist, max_dist = dists.min(), dists.max()
            min_alt, max_alt = alts.min(), alts.max()
            
            # Initialize Cache
            if CACHED_PROFILE is None:
                try:
                    # Create separate image for profile
                    prof_img = Image.new('RGBA', (prof_w, prof_h), (0, 0, 0, 0))
                    prof_draw = ImageDraw.Draw(prof_img)
                    
                    # Calculate points
                    # Normalize x: 0 -> prof_w
                    # Normalize y: min_alt -> max_alt  mapped to prof_h -> 0
                    
                    points = []
                    # Sample for performance if needed, but linear iterating is fast enough for ~10k points usually?
                    # Let's sample every 10th point to be safe
                    
                    step = max(1, len(dists) // 500) # Ensure roughly 500 points max
                    
                    # Pre-calculate scales
                    scale_x = prof_w / (max_dist - min_dist) if max_dist > min_dist else 0
                    scale_y = prof_h / (max_alt - min_alt) if max_alt > min_alt else 0
                    
                    # Start point (bottom left)
                    points.append((0, prof_h))
                    
                    for i in range(0, len(dists), step):
                        d = dists.iloc[i]
                        a = alts.iloc[i]
                        
                        px = (d - min_dist) * scale_x
                        py = prof_h - (a - min_alt) * scale_y
                        points.append((px, py))
                    
                    # End point (bottom right)
                    points.append((points[-1][0], prof_h))
                    
                    if len(points) > 2:
                        prof_draw.polygon(points, fill=(100, 100, 100, 128), outline="white")
                        
                    CACHED_PROFILE = prof_img
                    PROFILE_W = prof_w
                    PROFILE_H = prof_h
                except Exception as e:
                    print(f"Profile init failed: {e}")
                    CACHED_PROFILE = None

            # Draw Profile
            if CACHED_PROFILE:
                img.paste(CACHED_PROFILE, (prof_x, prof_y), CACHED_PROFILE)
                
                # Draw Current Position Indicator
                curr_dist = data_row.get('distance')
                if pd.notna(curr_dist):
                    # Project current distance
                     # Re-calc scale or store it? Recalc is cheap.
                    scale_x = PROFILE_W / (max_dist - min_dist) if max_dist > min_dist else 0
                    
                    px = prof_x + (curr_dist - min_dist) * scale_x
                    
                    # Draw vertical line
                    draw.line((px, prof_y, px, prof_y + PROFILE_H), fill="yellow", width=2)
 


    return img

def create_frame(t, data_row, width, height, bg_color=(0, 0, 0, 0)):
    img = create_frame_rgba(t, data_row, width, height, bg_color)
    return np.array(img)
