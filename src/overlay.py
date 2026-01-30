from PIL import Image, ImageDraw, ImageFont
import numpy as np
import pandas as pd

def create_frame(t, data_row, width, height):
    """
    Creates a transparent PIL image with the HUD overlay for a specific time t.
    """
    # Create a transparent image
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Define fonts - Assuming default loadable fonts or system fonts. 
    # Since we can't easily rely on specific font files being present, we try a few or fallback to default.
    try:
        # A nice thick font for numbers
        font_large = ImageFont.truetype("DejaVuSans-Bold.ttf", 100)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 30)
        font_label = ImageFont.truetype("DejaVuSans.ttf", 20)
    except IOError:
        try:
             # Fallback for linux usually
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 100)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
            font_label = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except IOError:
             # Ultimate fallback
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_label = ImageFont.load_default()

    # Layout configuration
    margin_left = 50
    margin_top = 100
    spacing = 150
    
    # 1. Speed
    speed_mph = data_row.get('speed_mph', 0)
    speed_kph = data_row.get('speed_kph', 0)
    
    # Draw MPH
    draw.text((margin_left, margin_top), f"{int(speed_mph)}", font=font_large, fill="white")
    draw.text((margin_left, margin_top + 100), "MPH", font=font_label, fill="white")
    
    # Draw KPH
    draw.text((margin_left, margin_top + 130), f"{int(speed_kph)}", font=font_large, fill="white")
    draw.text((margin_left, margin_top + 230), "KM/H", font=font_label, fill="white")
    
    # 2. Power
    power = data_row.get('power', 0)
    draw.text((margin_left, margin_top + 300), f"{int(power)}", font=font_large, fill="white")
    draw.text((margin_left, margin_top + 400), "W", font=font_label, fill="white")
    
    # 3. RPM
    cadence = data_row.get('cadence', 0)
    draw.text((margin_left, margin_top + 450), f"{int(cadence)}", font=font_large, fill="white")
    draw.text((margin_left, margin_top + 550), "RPM", font=font_label, fill="white")

    # 4. Gradient (if available, else placeholder)
    # grade might be in % or fraction, let's assume if it exists it's usually percentage in fit files but fitparse gives whatever is in file.
    # Usually 'grade' in fit is %.
    grade = data_row.get('grade', 0) # Assuming this column exists or was renamed properly
    # If grade is missing or nan, show 0
    if np.isnan(grade):
        grade = 0
    draw.text((margin_left, margin_top + 600), f"{grade:.1f}%", font=font_large, fill="white")
    draw.text((margin_left, margin_top + 700), "GRADIENT", font=font_label, fill="white")
    
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
            
            # Check for cached map or init
            if not hasattr(create_frame, "smopy_map"):
                import smopy
                try:
                    create_frame.smopy_map = smopy.Map(
                        (min_lat - lat_pad, min_lon - lon_pad, 
                         max_lat + lat_pad, max_lon + lon_pad), 
                        z=15 # fixed zoom? or auto
                    )
                    # or allow it to auto-zoom. but we need efficient bbox.
                    # smopy.Map(box_tuple)
                    print("Map initialized.")
                except Exception as e:
                    print(f"Map init failed: {e}")
                    create_frame.smopy_map = None

            map_obj = getattr(create_frame, "smopy_map", None)
            
            if map_obj:
                # Get the map image as PIL
                # smopy returns PIL image via to_pil()
                try:
                    map_img = map_obj.to_pil()
                    map_img = map_img.resize((map_size, map_size))
                    
                    # Convert to RGBA
                    map_img = map_img.convert("RGBA")
                    
                    # Paste map onto overlay
                    # Make it slightly transparent?
                    # img.paste(map_img, (map_x, map_y))
                    
                    # Draw a border
                    draw.rectangle((map_x-2, map_y-2, map_x+map_size+2, map_y+map_size+2), outline="white", width=2)
                    img.paste(map_img, (map_x, map_y))
                    
                    # Now we need to project lat/lon to pixels in this map image
                    # smopy.to_pixels(lat, lon) -> x, y (relative to original image size)
                    
                    # Helper for projection relative to the resized map
                    def project_point(lat, lon):
                        x, y = map_obj.to_pixels(lat, lon)
                        # Scale to new size
                        # original size
                        orig_w, orig_h = map_obj.img.size if hasattr(map_obj, 'img') and map_obj.img else map_obj.to_pil().size
                        
                        scale_x = map_size / orig_w
                        scale_y = map_size / orig_h
                        
                        sx = map_x + x * scale_x
                        sy = map_y + y * scale_y
                        return sx, sy

                    # Draw full path
                    # Sample points
                    points = []
                    # Optimization: maybe cache the path points too later?
                    for i in range(0, len(lats), 5): # sample 
                        px, py = project_point(lats.iloc[i], longs.iloc[i])
                        # clip?
                        points.append((px, py))
                    
                    if len(points) > 1:
                        draw.line(points, fill="blue", width=3) # Blue track on map

                    # Current pos
                    curr_lat = data_row.get('position_lat')
                    curr_lon = data_row.get('position_long')
                    if pd.notna(curr_lat) and pd.notna(curr_lon):
                        cx, cy = project_point(curr_lat, curr_lon)
                        r = 6
                        draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill="yellow", outline="black")

                except Exception as e:
                    print(e)
            else:
                # Fallback to old drawing if map failed
                pass 


    return np.array(img)
