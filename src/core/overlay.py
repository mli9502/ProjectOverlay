from PIL import Image, ImageDraw, ImageFont
import numpy as np
import pandas as pd


# Font path constant
FONT_PATH_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PATH_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Font cache for scaled fonts
FONT_CACHE = {}

def get_scaled_font(font_path, base_size, scale):
    """Get a scaled font, using cache to avoid recreating fonts."""
    key = (font_path, base_size, scale)
    if key not in FONT_CACHE:
        try:
            FONT_CACHE[key] = ImageFont.truetype(font_path, int(base_size * scale))
        except:
            FONT_CACHE[key] = ImageFont.load_default()
    return FONT_CACHE[key]

# Map cache globals
CACHED_BACKGROUND = None
MAP_OBJ = None

# Profile cache globals
CACHED_PROFILE = None
PROFILE_W = 0
PROFILE_H = 0


def create_frame_rgba(t, data_row, width, height, bg_color=(0, 0, 0, 0), config=None, layout_scale=1.0):
    """
    Creates a transparent PIL image with the HUD overlay for a specific time t.
    
    config: dict with component settings, e.g.:
        {'speed': {'enabled': True, 'scale': 1.0, 'opacity': 1.0}, ...}

    layout_scale: Scaling factor for resolution independence (e.g. 1.0 for 1080p, 0.33 for 360p).
    """
    # Default config if not provided
    if config is None:
        config = {
            'speed': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
            'power': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
            'cadence': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
            'gradient': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
            'map': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
            'elevation': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
            'heart_rate': {'enabled': True, 'scale': 1.0, 'opacity': 1.0},
        }
    
    def get_cfg(name):
        return config.get(name, {'enabled': True, 'scale': 1.0, 'opacity': 1.0})
    
    # Helper for layout scaling
    def sc(val):
        return int(val * layout_scale)
    
    # Create a background with bg_color (supports RGBA or RGB)
    img = Image.new('RGBA' if len(bg_color) == 4 else 'RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Layout configuration
    margin_left = sc(50)
    margin_top = sc(50)
    
    # 1. Speed (Top Left)
    cfg = get_cfg('speed')
    if cfg['enabled']:
        # Combine user scale preference with layout scale
        scale = cfg.get('scale', 1.0) * layout_scale
        font_large = get_scaled_font(FONT_PATH_BOLD, 80, scale)
        font_label = get_scaled_font(FONT_PATH_REGULAR, 20, scale)
        
        speed = data_row.get('speed_mph', 0)
        if pd.isna(speed): speed = 0
        
        opacity = int(255 * cfg['opacity'])
        color = (255, 255, 255, opacity)
        y_pos = margin_top
        draw.text((margin_left, y_pos), f"{speed:.0f}", font=font_large, fill=color)
        draw.text((margin_left, y_pos + int(80 * scale)), "MPH", font=font_label, fill=color)
    
    # 2. Power
    cfg = get_cfg('power')
    if cfg['enabled']:
        scale = cfg.get('scale', 1.0) * layout_scale
        font_large = get_scaled_font(FONT_PATH_BOLD, 80, scale)
        font_label = get_scaled_font(FONT_PATH_REGULAR, 20, scale)
        
        power = data_row.get('power', 0)
        if pd.isna(power): power = 0
        
        opacity = int(255 * cfg['opacity'])
        color = (255, 255, 255, opacity)
        y_pos = margin_top + sc(200)
        draw.text((margin_left, y_pos), f"{power:.0f}", font=font_large, fill=color)
        draw.text((margin_left, y_pos + int(80 * scale)), "W", font=font_label, fill=color)
    
    # 3. Cadence
    cfg = get_cfg('cadence')
    if cfg['enabled']:
        scale = cfg.get('scale', 1.0) * layout_scale
        font_large = get_scaled_font(FONT_PATH_BOLD, 80, scale)
        font_label = get_scaled_font(FONT_PATH_REGULAR, 20, scale)
        
        cadence = data_row.get('cadence', 0)
        if pd.isna(cadence): cadence = 0
        
        opacity = int(255 * cfg['opacity'])
        color = (255, 255, 255, opacity)
        y_pos = margin_top + sc(400)
        draw.text((margin_left, y_pos), f"{cadence:.0f}", font=font_large, fill=color)
        draw.text((margin_left, y_pos + int(80 * scale)), "RPM", font=font_label, fill=color)
    
    # 4. Heart Rate (Below Cadence)
    cfg = get_cfg('heart_rate')
    if cfg['enabled']:
        scale = cfg.get('scale', 1.0) * layout_scale
        font_large = get_scaled_font(FONT_PATH_BOLD, 80, scale)
        font_label = get_scaled_font(FONT_PATH_REGULAR, 20, scale)
        
        hr = data_row.get('heart_rate', 0)
        if pd.isna(hr): hr = 0
        
        opacity = int(255 * cfg['opacity'])
        color = (255, 255, 255, opacity)
        y_pos = margin_top + sc(600)
        draw.text((margin_left, y_pos), f"{hr:.0f}", font=font_large, fill=color)
        draw.text((margin_left, y_pos + int(80 * scale)), "BPM", font=font_label, fill=color)

    # 5. Gradient (Below HR)
    cfg = get_cfg('gradient')
    if cfg['enabled']:
        scale = cfg.get('scale', 1.0) * layout_scale
        font_large = get_scaled_font(FONT_PATH_BOLD, 80, scale)
        font_label = get_scaled_font(FONT_PATH_REGULAR, 20, scale)
        
        grade = data_row.get('grade', 0)
        if pd.isna(grade): grade = 0
        
        opacity = int(255 * cfg['opacity'])
        color = (255, 255, 255, opacity)
        y_pos = margin_top + sc(800)
        draw.text((margin_left, y_pos), f"{grade:.1f}%", font=font_large, fill=color)
        draw.text((margin_left, y_pos + int(80 * scale)), "GRADIENT", font=font_label, fill=color)
    
    # 6. Mini Map with Real Background
    cfg = get_cfg('map')
    if cfg['enabled']:
        full_track = data_row.get('full_track_df')
        if full_track is not None and not full_track.empty:
            # Map settings - apply scale
            user_scale = cfg.get('scale', 1.0)
            base_map_size = 300
            map_size = int(base_map_size * user_scale * layout_scale)
            
            # Ensure map_size is at least 1 pixel
            map_size = max(1, map_size)
            
            map_x = width - map_size - sc(50)
            map_y = sc(50)
            
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
                            
                            # Helper for projection
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
                    except Exception as e:
                        print(f"Map cache init failed: {e}")
                        CACHED_BACKGROUND = None

                # Use Cached Background
                if CACHED_BACKGROUND and MAP_OBJ:
                    # Resize if size changed (due to scale change)
                    current_cached_size = CACHED_BACKGROUND.size[0]
                    if map_size != current_cached_size:
                        map_copy = CACHED_BACKGROUND.resize((map_size, map_size), Image.LANCZOS)
                    else:
                        map_copy = CACHED_BACKGROUND.copy()
                    
                    # Apply opacity
                    map_opacity = cfg['opacity']
                    if map_opacity < 1.0:
                        r, g, b, a = map_copy.split()
                        a = a.point(lambda x: int(x * map_opacity))
                        map_copy = Image.merge('RGBA', (r, g, b, a))
                    
                    # 1. Paste Cached Map
                    draw.rectangle((map_x-2, map_y-2, map_x+map_size+2, map_y+map_size+2), outline="white", width=2)
                    img.paste(map_copy, (map_x, map_y), map_copy)
                    
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
                        
                        r = max(4, int(6 * user_scale * layout_scale))
                        draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill="yellow", outline="black")

    # 7. Elevation Profile (Bottom)
    cfg = get_cfg('elevation')
    if cfg['enabled']:
        full_track = data_row.get('full_track_df')
        if full_track is not None and not full_track.empty:
            # Profile settings - apply scale to height
            user_scale = cfg.get('scale', 1.0)
            base_prof_h = 150
            prof_h = int(base_prof_h * user_scale * layout_scale)
            prof_h = max(1, prof_h)
            
            prof_w = width - sc(100)
            prof_x = sc(50)
            prof_y = height - prof_h - sc(50)
            
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
                        
                        points = []
                        step = max(1, len(dists) // 500)
                        
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
                    # Resize if height scale changed (keep full width, only scale height)
                    target_h = prof_h
                    target_w = prof_w  # Keep full width
                    if target_h != PROFILE_H:
                        prof_copy = CACHED_PROFILE.resize((target_w, target_h), Image.LANCZOS)
                    else:
                        prof_copy = CACHED_PROFILE.copy()
                    
                    # Apply opacity
                    prof_opacity = cfg['opacity']
                    if prof_opacity < 1.0:
                        r, g, b, a = prof_copy.split()
                        a = a.point(lambda x: int(x * prof_opacity))
                        prof_copy = Image.merge('RGBA', (r, g, b, a))
                    img.paste(prof_copy, (prof_x, prof_y), prof_copy)
                    
                    # Draw Current Position Indicator
                    curr_dist = data_row.get('distance')
                    if pd.notna(curr_dist):
                        scale_x = PROFILE_W / (max_dist - min_dist) if max_dist > min_dist else 0
                        px = prof_x + (curr_dist - min_dist) * scale_x
                        draw.line((px, prof_y, px, prof_y + PROFILE_H), fill="yellow", width=2)


    return img

def create_frame(t, data_row, width, height, bg_color=(0, 0, 0, 0)):
    return np.array(create_frame_rgba(t, data_row, width, height, bg_color))
