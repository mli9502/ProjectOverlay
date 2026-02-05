// Browser Polyfill / Network Bridge
if (!window.api) {
    console.log('Running in browser mode');

    // Check if we are running from the Node server (localhost:3001)
    const isNodeServer = window.location.port === '3001';

    if (isNodeServer) {
        console.log('Detected Node Server - Activating Network Bridge');

        // File Browser State
        let fileBrowserResolve = null;
        let fileBrowserFilter = '';
        let selectedFilePath = null;
        let isSaveMode = false;
        let currentDirectory = '';

        // Initialize file browser when DOM is ready
        function initFileBrowser() {
            const modal = document.getElementById('file-browser-modal');
            const fileList = document.getElementById('file-list');
            const currentPathInput = document.getElementById('current-path');
            const selectBtn = document.getElementById('file-browser-select');
            const cancelBtn = document.getElementById('file-browser-cancel');
            const closeBtn = document.getElementById('file-browser-close');

            // Close handlers
            const closeModal = () => {
                modal.classList.add('hidden');
                if (fileBrowserResolve) {
                    fileBrowserResolve(null);
                    fileBrowserResolve = null;
                }
            };

            cancelBtn.addEventListener('click', closeModal);
            closeBtn.addEventListener('click', closeModal);
            modal.addEventListener('click', (e) => {
                if (e.target === modal) closeModal();
            });

            // Select handler
            selectBtn.addEventListener('click', () => {
                modal.classList.add('hidden');
                document.getElementById('filename-row').classList.add('hidden');

                if (fileBrowserResolve) {
                    if (isSaveMode) {
                        // In save mode, combine directory with filename
                        const filename = document.getElementById('output-filename').value.trim();
                        if (filename && currentDirectory) {
                            const fullPath = currentDirectory + '/' + filename;
                            fileBrowserResolve(fullPath);
                        } else {
                            fileBrowserResolve(null);
                        }
                    } else if (selectedFilePath) {
                        fileBrowserResolve(selectedFilePath);
                    } else {
                        fileBrowserResolve(null);
                    }
                    fileBrowserResolve = null;
                }
            });
        }

        // Load directory contents
        async function loadDirectory(dirPath, filter) {
            const fileList = document.getElementById('file-list');
            const currentPathInput = document.getElementById('current-path');
            const selectBtn = document.getElementById('file-browser-select');

            fileList.innerHTML = '<div style="padding: 20px; color: #8b949e;">Loading...</div>';
            selectedFilePath = null;
            selectBtn.disabled = true;

            try {
                const response = await fetch('/api/list-dir', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ dirPath, filter })
                });

                if (!response.ok) throw new Error('Failed to load directory');

                const data = await response.json();
                currentPathInput.value = data.currentPath;
                currentDirectory = data.currentPath;

                // In save mode, enable select button if filename is provided
                if (isSaveMode) {
                    const filenameInput = document.getElementById('output-filename');
                    selectBtn.disabled = !filenameInput.value.trim();
                }

                fileList.innerHTML = '';

                for (const item of data.items) {
                    const entry = document.createElement('div');
                    entry.className = 'file-entry' + (item.isDirectory ? ' directory' : '');
                    entry.innerHTML = `
                        <span class="file-entry-icon">${item.isDirectory ? '📁' : '📄'}</span>
                        <span class="file-name">${item.name}</span>
                    `;

                    entry.addEventListener('click', () => {
                        if (item.isDirectory) {
                            // Navigate into directory
                            loadDirectory(item.path, fileBrowserFilter);
                        } else {
                            // Select file
                            document.querySelectorAll('.file-entry.selected').forEach(el => el.classList.remove('selected'));
                            entry.classList.add('selected');
                            selectedFilePath = item.path;
                            selectBtn.disabled = false;
                        }
                    });

                    // Double-click to select file immediately
                    if (!item.isDirectory) {
                        entry.addEventListener('dblclick', () => {
                            selectedFilePath = item.path;
                            document.getElementById('file-browser-select').click();
                        });
                    }

                    fileList.appendChild(entry);
                }

                if (data.items.length === 0) {
                    fileList.innerHTML = '<div style="padding: 20px; color: #8b949e;">No matching files found</div>';
                }
            } catch (err) {
                console.error('Load directory error:', err);
                fileList.innerHTML = `<div style="padding: 20px; color: #d29922;">Error: ${err.message}</div>`;
            }
        }

        // Open file browser dialog
        function openFileBrowser(title, filter) {
            return new Promise(async (resolve) => {
                fileBrowserResolve = resolve;
                fileBrowserFilter = filter;
                selectedFilePath = null;
                isSaveMode = false;

                document.getElementById('file-browser-title').textContent = title;
                document.getElementById('file-browser-select').disabled = true;
                document.getElementById('file-browser-select').textContent = 'Select';
                document.getElementById('filename-row').classList.add('hidden');
                document.getElementById('file-browser-modal').classList.remove('hidden');

                // Get home directory and load it
                try {
                    const res = await fetch('/api/home-dir');
                    const data = await res.json();
                    loadDirectory(data.path, filter);
                } catch (err) {
                    loadDirectory('/', filter);
                }
            });
        }

        // Open save dialog for choosing output location
        function openSaveDialog(title, defaultFilename) {
            return new Promise(async (resolve) => {
                fileBrowserResolve = resolve;
                fileBrowserFilter = '';  // Show all files/folders for navigation
                selectedFilePath = null;
                isSaveMode = true;

                document.getElementById('file-browser-title').textContent = title;
                document.getElementById('file-browser-select').disabled = true;
                document.getElementById('file-browser-select').textContent = 'Save';
                document.getElementById('filename-row').classList.remove('hidden');

                const filenameInput = document.getElementById('output-filename');
                filenameInput.value = defaultFilename || 'output.mp4';

                // Enable save button when filename is entered
                filenameInput.oninput = () => {
                    document.getElementById('file-browser-select').disabled = !filenameInput.value.trim();
                };

                document.getElementById('file-browser-modal').classList.remove('hidden');

                // Get home directory and load it
                try {
                    const res = await fetch('/api/home-dir');
                    const data = await res.json();
                    loadDirectory(data.path, '');
                } catch (err) {
                    loadDirectory('/', '');
                }
            });
        }

        // Initialize file browser when page loads
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initFileBrowser);
        } else {
            initFileBrowser();
        }

        window.api = {
            openVideoDialog: () => openFileBrowser('Select Video File', '.mp4,.mov,.avi,.mkv'),
            openFitDialog: () => openFileBrowser('Select FIT File', '.fit'),
            saveVideoDialog: (defaultName) => openSaveDialog('Save Output Video', defaultName || 'output_overlay.mp4'),

            getVideoInfo: async (params) => {
                const response = await fetch('/api/video-info', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(params)
                });
                if (!response.ok) throw new Error('Failed to fetch info');
                return response.json();
            },

            getPreview: async (params) => {
                const response = await fetch('/api/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(params)
                });
                if (!response.ok) throw new Error('Failed to generate preview');
                const data = await response.json();
                return data.image;
            },

            calculateSync: async (params) => {
                const response = await fetch('/api/calculate-sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(params)
                });
                if (!response.ok) throw new Error('Failed to calculate sync');
                return response.json();
            },

            generate: async (config) => {
                // Start Job
                const response = await fetch('/api/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });

                if (!response.ok) throw new Error('Failed to start');

                // Poll for progress
                return new Promise((resolve, reject) => {
                    const poll = setInterval(async () => {
                        try {
                            const res = await fetch('/api/status');
                            const job = await res.json();

                            if (window.browserProgressCallback) window.browserProgressCallback(job.progress);
                            if (window.browserStatusCallback) window.browserStatusCallback(job.message);

                            if (job.status === 'completed') {
                                clearInterval(poll);
                                resolve({ success: true, path: 'Output on Server' });
                            } else if (job.status === 'error') {
                                clearInterval(poll);
                                reject(new Error(job.message));
                            }
                        } catch (e) {
                            console.error('Poll error', e);
                        }
                    }, 1000);
                });
            },

            onProgress: (cb) => { window.browserProgressCallback = cb; },
            onStatus: (cb) => { window.browserStatusCallback = cb; }
        };
    } else {
        // Fallback for static file / unconnected simple browser test
        console.log('Running in Static/Disconnected Mode - Using Mock Polyfill');
        alert('Running in Browser Mode (Backend Simulated)');

        // ... (Keep existing Mock Polyfill logic for fallback if needed, or simplfy)
        // For brevity in this edit, I will just paste the Mock logic again below, 
        // or effectively the previous logic is used if !isNodeServer.

        const createFileInput = (accept) => {
            // ... existing createFileInput logic ...
            return new Promise((resolve) => {
                const input = document.createElement('input');
                input.type = 'file';
                input.accept = accept;
                input.style.position = 'absolute';
                input.style.visibility = 'hidden';
                input.style.top = '0';
                input.style.left = '0';
                document.body.appendChild(input);

                input.onchange = (e) => {
                    if (e.target.files.length > 0) {
                        resolve(e.target.files[0].name);
                    } else {
                        resolve(null);
                    }
                    setTimeout(() => document.body.removeChild(input), 100);
                };
                input.oncancel = () => {
                    resolve(null);
                    setTimeout(() => document.body.removeChild(input), 100);
                };
                input.click();
            });
        };

        window.api = {
            openVideoDialog: () => createFileInput('.mp4,.mov,.avi,.mkv'),
            openFitDialog: () => createFileInput('.fit'),
            saveVideoDialog: () => Promise.resolve('output_video.mp4'),
            getVideoInfo: (params) => {
                console.log('Mocking info', params);
                return Promise.resolve({ duration: 120, width: 1920, height: 1080, fps: 30 });
            },
            getPreview: () => Promise.resolve(''),
            generate: () => {
                return new Promise((resolve) => {
                    let progress = 0;
                    const interval = setInterval(() => {
                        progress += 10;
                        if (window.browserProgressCallback) window.browserProgressCallback(progress);
                        if (window.browserStatusCallback) window.browserStatusCallback(`Simulating... ${progress}%`);
                        if (progress >= 100) {
                            clearInterval(interval);
                            resolve({ success: true, path: 'mock_output.mp4' });
                        }
                    }, 500);
                });
            },
            onProgress: (cb) => { window.browserProgressCallback = cb; },
            onStatus: (cb) => { window.browserStatusCallback = cb; }
        };
    }
}

// State
const state = {
    videoPath: null,
    fitPath: null,
    duration: 0,
    textScale: 1.0,  // Global text scale
    textOpacity: 1.0,  // Global text opacity
    config: {
        speed: { enabled: true, scale: 1.0, opacity: 1.0 },
        power: { enabled: true, scale: 1.0, opacity: 1.0 },
        cadence: { enabled: true, scale: 1.0, opacity: 1.0 },
        heart_rate: { enabled: true, scale: 1.0, opacity: 1.0 },
        gradient: { enabled: true, scale: 1.0, opacity: 1.0 },
        map: { enabled: true, scale: 1.0, opacity: 1.0 },
        elevation: { enabled: true, 'scale': 1.0, opacity: 1.0 }
    }
};

// Text metrics (toggle only, share global size)
const textMetrics = [
    { id: 'speed', name: 'Speed (MPH)', icon: '🏃' },
    { id: 'power', name: 'Power (W)', icon: '⚡' },
    { id: 'cadence', name: 'Cadence (RPM)', icon: '🔄' },
    { id: 'heart_rate', name: 'Heart Rate (BPM)', icon: '❤️' },
    { id: 'gradient', name: 'Gradient (%)', icon: '📈' }
];

// Visual components (have size + opacity controls)
const visualComponents = [
    { id: 'map', name: 'Mini Map', icon: '🗺️' },
    { id: 'elevation', name: 'Elevation Profile', icon: '⛰️' }
];

// Initialize UI
function initComponents() {
    const container = document.getElementById('components-list');

    // Global text size and opacity control
    const globalCard = document.createElement('div');
    globalCard.className = 'component-card';
    globalCard.innerHTML = `
        <div class="component-header">
            <label>📊 Text Metrics</label>
        </div>
        <div class="component-controls">
            <span>Size</span>
            <input type="range" id="global-text-scale" min="50" max="200" value="100">
            <span id="global-text-scale-val">100%</span>
        </div>
        <div class="component-controls">
            <span>Opacity</span>
            <input type="range" id="global-text-opacity" min="0" max="100" value="100">
            <span id="global-text-opacity-val">100%</span>
        </div>
    `;
    container.appendChild(globalCard);

    document.getElementById('global-text-scale').addEventListener('input', (e) => {
        const val = e.target.value;
        state.textScale = val / 100;
        document.getElementById('global-text-scale-val').textContent = `${val}%`;
        // Apply to all text metrics
        textMetrics.forEach(m => state.config[m.id].scale = state.textScale);
        debouncePreview();
    });

    document.getElementById('global-text-opacity').addEventListener('input', (e) => {
        const val = e.target.value;
        state.textOpacity = val / 100;
        document.getElementById('global-text-opacity-val').textContent = `${val}%`;
        // Apply to all text metrics
        textMetrics.forEach(m => state.config[m.id].opacity = state.textOpacity);
        debouncePreview();
    });

    // Text metrics (toggle only)
    textMetrics.forEach(comp => {
        const card = document.createElement('div');
        card.className = 'component-card compact';
        card.innerHTML = `
            <div class="component-header">
                <input type="checkbox" id="${comp.id}-enabled" checked>
                <label for="${comp.id}-enabled">${comp.icon} ${comp.name}</label>
            </div>
        `;
        container.appendChild(card);

        document.getElementById(`${comp.id}-enabled`).addEventListener('change', (e) => {
            state.config[comp.id].enabled = e.target.checked;
            debouncePreview();
        });
    });

    // Visual components (size + opacity)
    visualComponents.forEach(comp => {
        const card = document.createElement('div');
        card.className = 'component-card';
        card.innerHTML = `
            <div class="component-header">
                <input type="checkbox" id="${comp.id}-enabled" checked>
                <label for="${comp.id}-enabled">${comp.icon} ${comp.name}</label>
            </div>
            <div class="component-controls">
                <span>Size</span>
                <input type="range" id="${comp.id}-scale" min="50" max="200" value="100">
                <span id="${comp.id}-scale-val">100%</span>
            </div>
            <div class="component-controls">
                <span>Opacity</span>
                <input type="range" id="${comp.id}-opacity" min="0" max="100" value="100">
                <span id="${comp.id}-opacity-val">100%</span>
            </div>
        `;
        container.appendChild(card);

        document.getElementById(`${comp.id}-enabled`).addEventListener('change', (e) => {
            state.config[comp.id].enabled = e.target.checked;
            debouncePreview();
        });

        document.getElementById(`${comp.id}-scale`).addEventListener('input', (e) => {
            const val = e.target.value;
            state.config[comp.id].scale = val / 100;
            document.getElementById(`${comp.id}-scale-val`).textContent = `${val}%`;
            debouncePreview();
        });

        document.getElementById(`${comp.id}-opacity`).addEventListener('input', (e) => {
            const val = e.target.value;
            state.config[comp.id].opacity = val / 100;
            document.getElementById(`${comp.id}-opacity-val`).textContent = `${val}%`;
            debouncePreview();
        });
    });
}

// File selection handlers
document.getElementById('btn-video').addEventListener('click', async () => {
    const path = await window.api.openVideoDialog();
    if (path) {
        state.videoPath = path;
        document.getElementById('video-name').textContent = path.split(/[/\\]/).pop();

        // Get actual video duration
        try {
            const videoInfo = await window.api.getVideoInfo({ videoPath: path });
            state.duration = Math.floor(videoInfo.duration);
            document.getElementById('timeline').max = state.duration;
            document.getElementById('timeline').disabled = false;
        } catch (error) {
            console.error('Failed to get video info:', error);
            state.duration = 300; // Fallback
        }

        checkReady();
        if (state.fitPath) updatePreview();
    }
});

document.getElementById('btn-fit').addEventListener('click', async () => {
    const path = await window.api.openFitDialog();
    if (path) {
        state.fitPath = path;
        document.getElementById('fit-name').textContent = path.split(/[/\\]/).pop();
        checkReady();
        if (state.videoPath) updatePreview();
    }
});

// Check if ready to generate
function checkReady() {
    const ready = state.videoPath && state.fitPath;
    document.getElementById('btn-generate').disabled = !ready;

    // Calculate sync offset if ready
    if (ready) {
        document.getElementById('sync-status').textContent = 'Calculating sync...';
        window.api.calculateSync({ videoPath: state.videoPath, fitPath: state.fitPath })
            .then(data => {
                if (data.success) {
                    const offset = data.offset.toFixed(2);
                    document.getElementById('sync-status').innerHTML = `Sync Offset: <b>${offset}s</b> <br><small style="font-size:0.8em; opacity:0.8">Video: ${data.video_created}<br>FIT: ${data.fit_start}</small>`;
                    document.getElementById('sync-status').style.color = 'var(--text-primary)';
                } else {
                    document.getElementById('sync-status').textContent = 'Sync Failed: ' + data.message;
                    document.getElementById('sync-status').style.color = '#ff6b6b';
                }
            })
            .catch(err => {
                document.getElementById('sync-status').textContent = 'Sync Error';
                console.error(err);
            });
    } else {
        document.getElementById('sync-status').textContent = '';
    }
}

// Preview
let previewTimeout = null;
function debouncePreview() {
    if (previewTimeout) clearTimeout(previewTimeout);
    previewTimeout = setTimeout(updatePreview, 200);
}

async function updatePreview() {
    if (!state.fitPath || !state.videoPath) return;

    const timestamp = parseInt(document.getElementById('timeline').value);
    const minutes = Math.floor(timestamp / 60);
    const seconds = timestamp % 60;
    document.getElementById('time-display').textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;

    try {
        const base64Image = await window.api.getPreview({
            fitPath: state.fitPath,
            videoPath: state.videoPath,
            timestamp: timestamp,
            config: state.config
        });

        const img = document.getElementById('preview-img');
        img.src = `data:image/png;base64,${base64Image}`;
        img.classList.remove('hidden');
        document.getElementById('preview-placeholder').classList.add('hidden');
    } catch (error) {
        console.error('Preview error:', error);
    }
}

document.getElementById('timeline').addEventListener('input', debouncePreview);

// Generate
document.getElementById('btn-generate').addEventListener('click', async () => {
    // Suggest filename based on input video
    const videoBasename = state.videoPath ? state.videoPath.split(/[/\\]/).pop().replace(/\.[^.]+$/, '') : 'output';
    const outputPath = await window.api.saveVideoDialog(videoBasename + '_overlay.mp4');
    if (!outputPath) return;

    const btn = document.getElementById('btn-generate');
    btn.disabled = true;
    btn.textContent = 'Generating...';

    const progressContainer = document.getElementById('progress-container');
    progressContainer.classList.remove('hidden');

    try {
        const qualityMode = document.getElementById('quality-mode').value;
        await window.api.generate({
            fitPath: state.fitPath,
            videoPath: state.videoPath,
            outputPath: outputPath,
            config: state.config,
            quality: qualityMode
        });

        btn.textContent = 'Complete!';
        setTimeout(() => {
            btn.textContent = 'Generate Video';
            btn.disabled = false;
            progressContainer.classList.add('hidden');
        }, 2000);
    } catch (error) {
        console.error('Generate error:', error);
        btn.textContent = 'Error - Retry';
        btn.disabled = false;
    }
});

// Progress listener
window.api.onProgress((progress) => {
    document.getElementById('progress-fill').style.width = `${progress}%`;
    document.getElementById('progress-text').textContent = `${progress}%`;
});

// Status listener
window.api.onStatus((status) => {
    document.getElementById('progress-text').textContent = status;
});

// Initialize
initComponents();

// Server Health Check
(function initHealthCheck() {
    let serverConnected = true;

    // Create disconnection banner
    const banner = document.createElement('div');
    banner.id = 'server-disconnected-banner';
    banner.innerHTML = '⚠️ Server disconnected - Please restart the server';
    banner.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        background: #dc3545;
        color: white;
        padding: 10px;
        text-align: center;
        font-weight: bold;
        z-index: 10000;
        display: none;
    `;
    document.body.prepend(banner);

    async function checkHealth() {
        try {
            const response = await fetch('/api/status', {
                method: 'GET',
                signal: AbortSignal.timeout(3000)
            });
            if (response.ok) {
                if (!serverConnected) {
                    console.log('Server reconnected');
                    serverConnected = true;
                    banner.style.display = 'none';
                }
            } else {
                throw new Error('Server returned error');
            }
        } catch (err) {
            if (serverConnected) {
                console.warn('Server disconnected:', err.message);
                serverConnected = false;
                banner.style.display = 'block';
            }
        }
    }

    // Check every 5 seconds
    setInterval(checkHealth, 5000);
    // Initial check
    checkHealth();
})();
