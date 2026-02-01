const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let pythonProcess = null;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false
        },
        icon: path.join(__dirname, 'src/web/icon.png')
    });

    mainWindow.loadFile('src/web/index.html');

    // Open DevTools in development
    if (process.env.NODE_ENV === 'development') {
        mainWindow.webContents.openDevTools();
    }
}

app.whenReady().then(() => {
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on('window-all-closed', () => {
    if (pythonProcess) {
        pythonProcess.kill();
    }
    if (process.platform !== 'darwin') app.quit();
});

// IPC Handlers

// File dialogs
ipcMain.handle('dialog:openVideo', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openFile'],
        filters: [{ name: 'Video Files', extensions: ['mp4', 'MP4', 'mov', 'MOV', 'avi', 'AVI'] }]
    });
    return result.filePaths[0] || null;
});

ipcMain.handle('dialog:openFit', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openFile'],
        filters: [{ name: 'FIT Files', extensions: ['fit', 'FIT'] }]
    });
    return result.filePaths[0] || null;
});

ipcMain.handle('dialog:saveVideo', async () => {
    const result = await dialog.showSaveDialog(mainWindow, {
        defaultPath: 'output.mp4',
        filters: [{ name: 'MP4 Video', extensions: ['mp4'] }]
    });
    return result.filePath || null;
});

// Get video metadata
ipcMain.handle('python:getVideoInfo', async (event, { videoPath }) => {
    return new Promise((resolve, reject) => {
        const pythonScript = path.join(__dirname, 'src/api/get_video_info.py');
        const venvPython = path.join(__dirname, '.venv/bin/python');

        const proc = spawn(venvPython, [pythonScript, '--video', videoPath]);
        let stdout = '';
        let stderr = '';

        proc.stdout.on('data', (data) => { stdout += data.toString(); });
        proc.stderr.on('data', (data) => { stderr += data.toString(); });

        proc.on('close', (code) => {
            if (code === 0) {
                resolve(JSON.parse(stdout.trim()));
            } else {
                reject(new Error(stderr));
            }
        });
    });
});

// Python backend communication
ipcMain.handle('python:getPreview', async (event, { fitPath, videoPath, timestamp, config }) => {
    return new Promise((resolve, reject) => {
        const pythonScript = path.join(__dirname, 'src/api/preview_server.py');
        const venvPython = path.join(__dirname, '.venv/bin/python');

        const args = [
            pythonScript,
            '--fit', fitPath,
            '--video', videoPath,
            '--timestamp', timestamp.toString(),
            '--config', JSON.stringify(config)
        ];

        const proc = spawn(venvPython, args);
        let stdout = '';
        let stderr = '';

        proc.stdout.on('data', (data) => { stdout += data.toString(); });
        proc.stderr.on('data', (data) => { stderr += data.toString(); });

        proc.on('close', (code) => {
            if (code === 0) {
                resolve(stdout.trim());  // Base64 encoded image
            } else {
                reject(new Error(stderr));
            }
        });
    });
});

ipcMain.handle('python:generate', async (event, { fitPath, videoPath, outputPath, config }) => {
    return new Promise((resolve, reject) => {
        const pythonScript = path.join(__dirname, 'src/api/generate.py');
        const venvPython = path.join(__dirname, '.venv/bin/python');

        pythonProcess = spawn(venvPython, [
            pythonScript,
            '--fit', fitPath,
            '--video', videoPath,
            '--output', outputPath,
            '--config', JSON.stringify(config)
        ]);

        pythonProcess.stdout.on('data', (data) => {
            const lines = data.toString().trim().split('\n');
            lines.forEach(line => {
                if (line.startsWith('STATUS:')) {
                    const status = line.substring(7);
                    mainWindow.webContents.send('generation:status', status);
                } else if (line.startsWith('PROGRESS:')) {
                    const progress = parseInt(line.split(':')[1]);
                    mainWindow.webContents.send('generation:progress', progress);
                }
            });
        });

        pythonProcess.stderr.on('data', (data) => {
            console.error('Python error:', data.toString());
        });

        pythonProcess.on('close', (code) => {
            pythonProcess = null;
            if (code === 0) {
                resolve({ success: true, path: outputPath });
            } else {
                reject(new Error(`Generation failed with code ${code}`));
            }
        });
    });
});
