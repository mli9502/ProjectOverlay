const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
    // File dialogs
    openVideoDialog: () => ipcRenderer.invoke('dialog:openVideo'),
    openFitDialog: () => ipcRenderer.invoke('dialog:openFit'),
    saveVideoDialog: () => ipcRenderer.invoke('dialog:saveVideo'),

    // Python backend
    getVideoInfo: (params) => ipcRenderer.invoke('python:getVideoInfo', params),
    getPreview: (params) => ipcRenderer.invoke('python:getPreview', params),
    generate: (params) => ipcRenderer.invoke('python:generate', params),

    // Progress listener
    onProgress: (callback) => ipcRenderer.on('generation:progress', (event, progress) => callback(progress)),
    onStatus: (callback) => ipcRenderer.on('generation:status', (event, status) => callback(status))
});
