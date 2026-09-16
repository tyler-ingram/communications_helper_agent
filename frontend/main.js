const { app, BrowserWindow, ipcMain } = require('electron/main');
const fs = require('fs');
const path = require('node:path');

function createWindow() {
    const win = new BrowserWindow({
        width: 800,
        height: 600,
        webPreferences: {
            nodeIntegration: true,
            preload: path.join(__dirname, 'preload.js'),
        }
    });

    win.loadFile('index.html');
}

app.whenReady().then(() => {
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    })
})

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
})

ipcMain.on('submit-text-transcript', (event, formData) => {
    console.log('Received text transcript:', formData.text);
    // Here you can handle the text transcript, e.g., save it to a file or process it.
})

ipcMain.on('submit-file-transcript', (event, formData) => {
    console.log('Received file transcript:', formData.file);
    // Here you can handle the file transcript, e.g., save it to a file or process it.
})