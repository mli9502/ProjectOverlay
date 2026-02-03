const express = require('express');
const cors = require('cors');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = 3001;

// Python path - use virtualenv
const PYTHON_PATH = path.join(__dirname, '..', '.venv', 'bin', 'python3');

app.use(cors());
app.use(express.json());

// Log requests
app.use((req, res, next) => {
    console.log(`${new Date().toISOString()} ${req.method} ${req.url}`);
    next();
});

// Log requests
app.use((req, res, next) => {
    console.log(`${new Date().toISOString()} ${req.method} ${req.url}`);
    next();
});

// Serve static files from src/web
app.use(express.static(path.join(__dirname, 'web')));

// Fallback to index.html for root path if needed, though static middleware usually handles it
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'web', 'index.html'));
});

// API: Get home directory
app.get('/api/home-dir', (req, res) => {
    res.json({ path: require('os').homedir() });
});

// API: List directory contents for file browser
app.post('/api/list-dir', (req, res) => {
    try {
        const { dirPath, filter } = req.body;
        const targetPath = dirPath || require('os').homedir();

        if (!fs.existsSync(targetPath)) {
            return res.status(404).json({ error: 'Directory not found' });
        }

        const stats = fs.statSync(targetPath);
        if (!stats.isDirectory()) {
            return res.status(400).json({ error: 'Not a directory' });
        }

        const entries = fs.readdirSync(targetPath, { withFileTypes: true });
        const items = [];

        // Add parent directory entry if not at root
        if (targetPath !== '/') {
            items.push({
                name: '..',
                isDirectory: true,
                path: path.dirname(targetPath)
            });
        }

        for (const entry of entries) {
            // Skip hidden files
            if (entry.name.startsWith('.')) continue;

            const fullPath = path.join(targetPath, entry.name);
            const isDir = entry.isDirectory();

            // Apply filter for files
            if (!isDir && filter) {
                const ext = path.extname(entry.name).toLowerCase();
                const extensions = filter.split(',').map(e => e.trim().toLowerCase());
                if (!extensions.some(e => ext === e || ext === '.' + e)) {
                    continue;
                }
            }

            items.push({
                name: entry.name,
                isDirectory: isDir,
                path: fullPath
            });
        }

        // Sort: directories first, then files, both alphabetically
        items.sort((a, b) => {
            if (a.name === '..') return -1;
            if (b.name === '..') return 1;
            if (a.isDirectory && !b.isDirectory) return -1;
            if (!a.isDirectory && b.isDirectory) return 1;
            return a.name.localeCompare(b.name);
        });

        res.json({
            currentPath: targetPath,
            items
        });
    } catch (err) {
        console.error('List dir error:', err);
        res.status(500).json({ error: err.message });
    }
});

// Helper to spawn Python
function runPython(script, args) {
    return new Promise((resolve, reject) => {
        const pythonProcess = spawn(PYTHON_PATH, [script, ...args]);

        let stdout = '';
        let stderr = '';

        pythonProcess.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        pythonProcess.stderr.on('data', (data) => {
            stderr += data.toString();
        });

        pythonProcess.on('close', (code) => {
            if (code !== 0) {
                reject(stderr || `Exited with code ${code}`);
            } else {
                resolve(stdout);
            }
        });
    });
}

// Global job state (simple version for single user)
let currentJob = {
    status: 'idle',
    progress: 0,
    message: ''
};

// API: Get Video Info
app.post('/api/video-info', async (req, res) => {
    try {
        const { videoPath } = req.body;
        if (!videoPath) return res.status(400).json({ error: 'Missing videoPath' });

        const scriptPath = path.join(__dirname, 'api', 'get_video_info.py');
        const output = await runPython(scriptPath, ['--video', videoPath]);

        // Parse JSON output from script
        const data = JSON.parse(output);
        res.json(data);
    } catch (err) {
        console.error('Video info error:', err);
        res.status(500).json({ error: err.toString() });
    }
});

// API: Calculate Sync Offset
app.post('/api/calculate-sync', async (req, res) => {
    try {
        const { fitPath, videoPath } = req.body;
        if (!fitPath || !videoPath) {
            return res.status(400).json({ error: 'Missing fitPath or videoPath' });
        }

        const scriptPath = path.join(__dirname, 'api', 'calculate_sync.py');
        const output = await runPython(scriptPath, [
            '--fit', fitPath,
            '--video', videoPath
        ]);

        const data = JSON.parse(output);
        res.json(data);
    } catch (err) {
        console.error('Sync calculation error:', err);
        res.status(500).json({ error: err.toString() });
    }
});

// API: Preview - Generate a single frame preview
app.post('/api/preview', async (req, res) => {
    try {
        const { fitPath, videoPath, timestamp, config } = req.body;
        if (!fitPath || !videoPath) {
            return res.status(400).json({ error: 'Missing fitPath or videoPath' });
        }

        const scriptPath = path.join(__dirname, 'api', 'preview_server.py');
        const configStr = JSON.stringify(config || {});

        const output = await runPython(scriptPath, [
            '--fit', fitPath,
            '--video', videoPath,
            '--timestamp', String(timestamp || 0),
            '--config', configStr
        ]);

        // Output is base64 encoded image
        res.json({ image: output.trim() });
    } catch (err) {
        console.error('Preview error:', err);
        res.status(500).json({ error: err.toString() });
    }
});

// API: Check Health/Status
app.get('/api/status', (req, res) => {
    res.json(currentJob);
});

// API: Generate Overlay
// This spawns the process and updates global state
app.post('/api/generate', (req, res) => {
    if (currentJob.status === 'running') {
        return res.status(409).json({ error: 'Job already running' });
    }

    const { videoPath, fitPath, outputPath, config } = req.body;

    // Reset state
    currentJob = {
        status: 'running',
        progress: 0,
        message: 'Starting...'
    };

    // Serialize config
    const configStr = JSON.stringify(config);
    const scriptPath = path.join(__dirname, 'api', 'generate.py');

    console.log('Starting generation for:', videoPath);
    console.log('Output path:', outputPath);

    const child = spawn(PYTHON_PATH, [
        scriptPath,
        '--fit', fitPath,
        '--video', videoPath,
        '--output', outputPath,
        '--config', configStr
    ]);

    // Non-blocking response
    res.json({ success: true, message: 'Job started' });

    // Handle streaming output
    child.stdout.on('data', (data) => {
        const lines = data.toString().split('\n');
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) continue;

            console.log('PY:', trimmed);

            if (trimmed.startsWith('PROGRESS:')) {
                const parts = trimmed.split(':');
                if (parts.length >= 2) {
                    currentJob.progress = parseInt(parts[1], 10);
                }
            } else if (trimmed.startsWith('STATUS:')) {
                currentJob.message = trimmed.substring(7).trim();
            }
        }
    });

    child.stderr.on('data', (data) => {
        console.error('PY ERR:', data.toString());
    });

    child.on('close', (code) => {
        console.log('Job finished with code', code);
        currentJob.status = code === 0 ? 'completed' : 'error';
        currentJob.progress = 100;
        if (code !== 0) {
            currentJob.message = 'Detailed error in server logs';
        } else {
            currentJob.message = 'Done!';
        }
    });
});

app.listen(PORT, () => {
    console.log(`Server running at http://localhost:${PORT}`);
    console.log('Serving frontend from headers');
});
