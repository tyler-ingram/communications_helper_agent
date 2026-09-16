document.getElementById('text-transcript').addEventListener('submit', (event) => {
    event.preventDefault();

    const formData = {
        text: document.getElementById('transcript').value
    }

    window.api.submitTextTranscript(formData);
})

document.getElementById('file-transcript').addEventListener('submit', (event) => {
    event.preventDefault();

    const formData = {
        file: document.getElementById('file').files[0]
    }

    window.api.submitFileTranscript(formData);
})