const { app, BrowserWindow, Menu, ipcMain, shell, safeStorage } = require('electron/main');
const fs = require('fs');
const path = require('node:path');
const http = require('node:http');
const https = require('node:https');

const PROTOCOL = 'commshelper';
const API_BASE = 'http://127.0.0.1:8743';
const TOKEN_FILE = () => path.join(app.getPath('userData'), 'github-token.enc');

let mainWindow = null;
let githubToken = null; // plaintext, main-process memory only, never sent to renderer
let pendingSignIn = null; // { resolve, reject }

function apiRequest(method, urlPath, { body, token } = {}) {
    return new Promise((resolve, reject) => {
        const url = new URL(urlPath, API_BASE);
        const payload = body ? JSON.stringify(body) : null;
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        if (payload) headers['Content-Length'] = Buffer.byteLength(payload);

        const req = http.request(
            { hostname: url.hostname, port: url.port, path: url.pathname + url.search, method, headers },
            (res) => {
                let data = '';
                res.on('data', (chunk) => (data += chunk));
                res.on('end', () => {
                    let parsed;
                    try {
                        parsed = data ? JSON.parse(data) : {};
                    } catch (e) {
                        return reject(new Error(`Invalid JSON response from backend: ${data}`));
                    }
                    if (res.statusCode >= 200 && res.statusCode < 300) {
                        resolve(parsed);
                    } else {
                        reject(new Error(parsed.detail || `Backend request failed with status ${res.statusCode}`));
                    }
                });
            }
        );
        req.on('error', reject);
        if (payload) req.write(payload);
        req.end();
    });
}

function loadStoredToken() {
    try {
        if (!fs.existsSync(TOKEN_FILE())) return null;
        if (!safeStorage.isEncryptionAvailable()) {
            console.error('OS-level encryption is not available; cannot decrypt stored GitHub token.');
            return null;
        }
        const encrypted = fs.readFileSync(TOKEN_FILE());
        return safeStorage.decryptString(encrypted);
    } catch (err) {
        console.error('Failed to load stored GitHub token:', err.message);
        return null;
    }
}

function storeToken(token) {
    if (!safeStorage.isEncryptionAvailable()) {
        throw new Error('OS-level encryption is not available on this system; cannot securely store the GitHub token.');
    }
    const encrypted = safeStorage.encryptString(token);
    fs.mkdirSync(path.dirname(TOKEN_FILE()), { recursive: true });
    fs.writeFileSync(TOKEN_FILE(), encrypted);
}

async function handleOAuthCallback(url) {
    if (!pendingSignIn) return;
    try {
        const parsed = new URL(url);
        const code = parsed.searchParams.get('code');
        const state = parsed.searchParams.get('state');
        if (!code || !state) {
            throw new Error('OAuth callback missing code or state parameter');
        }

        const exchangeResult = await apiRequest('POST', '/auth/exchange', { body: { code, state } });
        const token = exchangeResult.access_token;
        if (!token) throw new Error('No access token returned from backend');

        storeToken(token);
        githubToken = token;

        const { resolve } = pendingSignIn;
        pendingSignIn = null;
        resolve({ signedIn: true });
    } catch (err) {
        const { reject } = pendingSignIn;
        pendingSignIn = null;
        reject(err);
    }
}

function parseProtocolUrlFromArgv(argv) {
    return argv.find((arg) => arg.startsWith(`${PROTOCOL}://`)) || null;
}

function registerProtocolHandler() {
    if (!app.isPackaged) {
        app.setAsDefaultProtocolClient(PROTOCOL, process.execPath, [path.resolve(process.argv[1])]);
    } else {
        app.setAsDefaultProtocolClient(PROTOCOL);
    }
}

function buildAppMenu() {
    const template = [
        {
            label: 'File',
            submenu: [
                { role: 'quit' }
            ]
        },
        {
            label: 'Edit',
            submenu: [
                { role: 'undo' },
                { role: 'redo' },
                { type: 'separator' },
                { role: 'cut' },
                { role: 'copy' },
                { role: 'paste' },
                { role: 'selectAll' }
            ]
        },
        {
            label: 'View',
            submenu: [
                { role: 'reload' },
                { role: 'forceReload' },
                { role: 'toggleDevTools' },
                { type: 'separator' },
                { role: 'resetZoom' },
                { role: 'zoomIn' },
                { role: 'zoomOut' },
                { type: 'separator' },
                { role: 'togglefullscreen' }
            ]
        },
        {
            label: 'Window',
            role: 'windowMenu'
        }
    ];

    Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 800,
        height: 600,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js'),
        }
    });

    mainWindow.loadFile('index.html');
    mainWindow.maximize();
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
    app.quit();
} else {
    app.on('second-instance', (event, argv) => {
        const url = parseProtocolUrlFromArgv(argv);
        if (url) handleOAuthCallback(url);

        if (mainWindow) {
            if (mainWindow.isMinimized()) mainWindow.restore();
            mainWindow.focus();
        }
    });

    app.on('open-url', (event, url) => {
        event.preventDefault();
        handleOAuthCallback(url);
    });

    app.whenReady().then(() => {
        registerProtocolHandler();
        buildAppMenu();
        githubToken = loadStoredToken();
        createWindow();

        // Handle a cold start where the OS launched us directly via the protocol.
        const url = parseProtocolUrlFromArgv(process.argv);
        if (url) handleOAuthCallback(url);

        app.on('activate', () => {
            if (BrowserWindow.getAllWindows().length === 0) {
                createWindow();
            }
        })
    })
}

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
})

ipcMain.handle('github-sign-in', async () => {
    if (pendingSignIn) {
        throw new Error('A sign-in attempt is already in progress');
    }

    const { state } = await apiRequest('GET', '/auth/state');
    const { client_id: clientId } = await apiRequest('GET', '/auth/client-id');

    const authorizeUrl = new URL('https://github.com/login/oauth/authorize');
    authorizeUrl.searchParams.set('client_id', clientId);
    authorizeUrl.searchParams.set('redirect_uri', `${PROTOCOL}://oauth/callback`);
    authorizeUrl.searchParams.set('scope', 'repo');
    authorizeUrl.searchParams.set('state', state);

    const signInPromise = new Promise((resolve, reject) => {
        pendingSignIn = { resolve, reject };
    });

    await shell.openExternal(authorizeUrl.toString());

    return signInPromise;
});

ipcMain.handle('get-auth-status', async () => {
    if (!githubToken) {
        return { signedIn: false };
    }
    try {
        const me = await apiRequest('GET', '/auth/me', { token: githubToken });
        return { signedIn: true, username: me.login };
    } catch (err) {
        // Token is stored but no longer valid against GitHub.
        githubToken = null;
        return { signedIn: false };
    }
});

ipcMain.handle('submit-text-transcript', async (event, formData) => {
    if (!githubToken) {
        throw new Error('Please sign in with GitHub first.');
    }
    return apiRequest('POST', '/transcript/text', { body: { text: formData.text }, token: githubToken });
})

ipcMain.handle('submit-file-transcript', async (event, formData) => {
    if (!githubToken) {
        throw new Error('Please sign in with GitHub first.');
    }
    return apiRequest('POST', '/transcript/file', { body: { file: formData.file }, token: githubToken });
})

ipcMain.handle('submit-accepted-issues', async (event, issues) => {
    if (!githubToken) {
        throw new Error('Please sign in with GitHub first.');
    }
    return apiRequest('POST', '/issues/accepted', { body: { issues }, token: githubToken });
})