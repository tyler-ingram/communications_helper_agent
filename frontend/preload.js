window.addEventListener('DOMContentLoaded', () => {
    const replaceText = (selector, text) => {
        const element = document.getElementById(selector);
        if (element) element.innerText = text;
    }

    for (const dependency of ['chrome', 'node', 'electron']) {
        replaceText(`${dependency}-version`, process.versions[dependency]);
    }
})

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
    submitTextTranscript: (formData) => ipcRenderer.invoke('submit-text-transcript', formData),
    submitFileTranscript: (formData) => ipcRenderer.invoke('submit-file-transcript', formData),
    signInWithGithub: () => ipcRenderer.invoke('github-sign-in'),
    getAuthStatus: () => ipcRenderer.invoke('get-auth-status'),
    submitAcceptedIssues: (issues) => ipcRenderer.invoke('submit-accepted-issues', issues),
    versions: process.versions,
})