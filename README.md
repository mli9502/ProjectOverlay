# ProjectOverlay

A Python tool to overlay fitness data (Speed, Power, Cadence, Gradient) and a dynamic mini-map onto action camera video.

## Features
- **Dashboard Overlay**: Clean HUD showing current stats.
- **Dynamic Mini-Map**: Real-time track map with current position, using OpenStreetMap tiles (via `smopy`).
- **Synchronization**: Automatically syncs FIT data with video (currently configured for a specific time offset).

## Setup
1. Clone the repository.
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Usage
Run the main script:
```bash
python src/main.py
```
This produces `output_final.mp4` (or `output_30s.mp4` if configured for preview).

## TODO
1. Increase processing speed (currently ~5-6 fps).
2. Add elevation profile at the bottom of the overlay.