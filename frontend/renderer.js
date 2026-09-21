const signInButton = document.getElementById('github-signin');
const authStatus = document.getElementById('auth-status');
const resultArea = document.getElementById('result-area');

function setAuthStatus(status) {
    if (status.signedIn) {
        authStatus.innerText = status.username ? `Signed in as ${status.username}` : 'Signed in';
        signInButton.innerText = 'Signed in';
        signInButton.disabled = true;
    } else {
        authStatus.innerText = 'Not signed in';
        signInButton.innerText = 'Sign in with GitHub';
        signInButton.disabled = false;
    }
}

async function refreshAuthStatus() {
    const status = await window.api.getAuthStatus();
    setAuthStatus(status);
}

signInButton.addEventListener('click', async () => {
    signInButton.disabled = true;
    signInButton.innerText = 'Waiting for GitHub authorization...';
    try {
        await window.api.signInWithGithub();
        await refreshAuthStatus();
    } catch (err) {
        authStatus.innerText = `Sign-in failed: ${err.message}`;
        signInButton.disabled = false;
        signInButton.innerText = 'Sign in with GitHub';
    }
});

document.getElementById('text-transcript').addEventListener('submit', async (event) => {
    event.preventDefault();

    const formData = {
        text: document.getElementById('transcript').value
    }

    resultArea.innerText = 'Processing transcript...';
    try {
        const response = await window.api.submitTextTranscript(formData);
        resultArea.innerText = response.result;
    } catch (err) {
        resultArea.innerText = `Error: ${err.message}`;
    }
})

document.getElementById('file-transcript').addEventListener('submit', async (event) => {
    event.preventDefault();

    const file = document.getElementById('file').files[0];
    if (!file) return;

    resultArea.innerText = 'Processing transcript...';
    try {
        const text = await file.text();
        const response = await window.api.submitFileTranscript({ file: text });
        resultArea.innerText = response.result;
    } catch (err) {
        resultArea.innerText = `Error: ${err.message}`;
    }
})

window.addEventListener('DOMContentLoaded', () => {
    const replaceText = (selector, text) => {
        const element = document.getElementById(selector);
        if (element) element.innerText = text;
    }

    for (const dependency of ['chrome', 'node', 'electron']) {
        replaceText(`${dependency}-version`, window.api.versions[dependency]);
    }

    refreshAuthStatus();
})
