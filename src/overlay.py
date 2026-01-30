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
    
    # 5. Mini Map
    full_track = data_row.get('full_track_df')
    if full_track is not None and not full_track.empty:
        # Map settings
        map_size = 300
        map_x = width - map_size - 50
        map_y = 50
        padding = 20
        
        # Get bounds
        lats = full_track['position_lat'].dropna()
        longs = full_track['position_long'].dropna()
        
        if not lats.empty and not longs.empty:
            min_lat, max_lat = lats.min(), lats.max()
            min_lon, max_lon = longs.min(), longs.max()
            
            # Helper to project
            def transform(lat, lon):
                # Simple linear projection (ok for small areas)
                # Normalize 0-1
                if max_lon == min_lon: x_norm = 0.5
                else: x_norm = (lon - min_lon) / (max_lon - min_lon)
                
                if max_lat == min_lat: y_norm = 0.5
                else: y_norm = (lat - min_lat) / (max_lat - min_lat)
                
                # Screen coords (flip y)
                sx = map_x + padding + x_norm * (map_size - 2 * padding)
                sy = map_y + map_size - padding - y_norm * (map_size - 2 * padding)
                return sx, sy

            # Draw full path
            # Reduce points for performance if needed, but we have small file
            # Collect points
            points = []
            # We can't iterate full df every frame efficiently? 
            # Ideally verify if 'full_track' is constant or if we should pre-calculate points.
            # For 5.0 complexity, let's just do it. Optimization later.
            # Actually, passing full dataframe every frame to this function is inefficient but simple.
            # Let's assume passed full_track has just the lat/lon columns.
            
            # Using numpy to calculate points fast
            # But PIL requires list of tuples
            
            # Let's just sample every 5th point for drawing speed
            for i in range(0, len(lats), 5):
                points.append(transform(lats.iloc[i], longs.iloc[i]))
            
            if len(points) > 1:
                draw.line(points, fill="white", width=3)
                
            # Draw current position
            curr_lat = data_row.get('position_lat')
            curr_lon = data_row.get('position_long')
            
            if pd.notna(curr_lat) and pd.notna(curr_lon):
                cx, cy = transform(curr_lat, curr_lon)
                r = 8
                draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill="yellow", outline="white")

    return np.array(img)
