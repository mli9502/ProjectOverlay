# ProjectOverlay

A hybrid Electron + Python application to overlay fitness data (Speed, Power, Cadence, Gradient) and a dynamic mini-map onto action camera video.

## Features
- **Dashboard Overlay**: Clean HUD showing current stats (Speed, Power, Elevation, etc.).
- **Dynamic Mini-Map**: Real-time track map with current position, using OpenStreetMap tiles.
- **Real-time Preview**: View your overlay synchronization in real-time before rendering.
- **Configurable Components**: Toggle and customize Speed, Power, Map, and Elevation widgets.
- **Synchronization**: Automatically syncs FIT data with video.

## Architecture
- **`src/web`**: Frontend GUI (HTML/CSS/JS) for configuration and preview.
- **`src/web_server.js`**: Node.js backend server providing REST APIs.
- **`src/api`**: Python scripts for video processing and overlay generation.

## Quick Start (Browser Interface)

### Prerequisites
- Node.js (v18+)
- Python 3.10+
- FFmpeg installed and in PATH

### Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd ProjectOverlay
   ```

2. **Install Node.js dependencies:**
   ```bash
   npm install
   ```

3. **Set up Python environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

### Running the Web Interface

1. **Start the server:**
   ```bash
   node src/web_server.js
   ```
   The server runs on port 3001 by default.

2. **Open in browser:**
   - **Local Access**: Navigate to `http://localhost:3001`
   - **WSL2 / Remote Access**: To access from Windows or other devices, you may need the internal WSL2 IP address:
     ```bash
     hostname -I | awk '{print $1}'
     ```
     Then navigate to `http://<YOUR_WSL_IP>:3001` (e.g., `http://172.22.x.x:3001`).

3. **Using the app:**
   - Click **"Select Video..."** to choose your action camera video (MP4, MOV, etc.)
   - Click **"Select FIT..."** to choose your Garmin/cycling FIT file
   - Use the **timeline slider** to preview different timestamps
   - Adjust overlay components (Text Metrics, Speed, Power, Map, Elevation) as needed
   - Click **"Generate Video"** to render the final output

### Output
The generated video will be saved alongside your original video with `_overlay` suffix:
- Input: `my_ride.mp4`
- Output: `my_ride_overlay.mp4`

## Alternative: Electron Desktop App

For the native desktop experience:
```bash
npm start
```
This launches the Electron GUI with native file dialogs.

## API Endpoints

The web server exposes these REST endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/home-dir` | GET | Get user's home directory |
| `/api/list-dir` | POST | List directory contents for file browser |
| `/api/video-info` | POST | Get video metadata (duration, dimensions, fps) |
| `/api/preview` | POST | Generate preview frame with overlay |
| `/api/generate` | POST | Start video generation job |
| `/api/status` | GET | Get current job progress and status |

## Requirements

See `requirements.txt` for Python dependencies. Key packages:
- `fitparse` - FIT file parsing
- `moviepy` - Video processing
- `pillow` - Image manipulation
- `pandas` - Data handling
- `staticmap` - Map tile rendering
