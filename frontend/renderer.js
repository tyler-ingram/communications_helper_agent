const signInButton = document.getElementById('github-signin');
const authStatus = document.getElementById('auth-status');
const resultArea = document.getElementById('result-area');
const currentTab = document.getElementById('current-tab');
const fileSubmitButton = document.getElementById('file-transcript')
const textSubmitButton = document.getElementById('text-transcript')

let lastRepoOwner = '';
let lastRepoName = '';
let isSignedIn = false;

function showError(message) {
    resultArea.innerText = message;
    resultArea.classList.add('app-result-error');
}

function showStatus(message) {
    resultArea.innerText = message;
    resultArea.classList.remove('app-result-error');
}

function setAuthStatus(status) {
    isSignedIn = status.signedIn;
    if (status.signedIn) {
        signInButton.innerText = status.username ? `Signed in as ${status.username}` : 'Signed in';
        signInButton.disabled = true;
    } else {
        signInButton.innerText = 'Sign in with GitHub';
        signInButton.disabled = false;
    }
}

async function refreshAuthStatus() {
    const status = await window.api.getAuthStatus();
    setAuthStatus(status);
}

async function beginSignIn() {
    signInButton.disabled = true;
    signInButton.innerText = 'Waiting for GitHub authorization...';
    try {
        await window.api.signInWithGithub();
        await refreshAuthStatus();
    } catch (err) {
        signInButton.disabled = false;
        signInButton.innerText = 'Sign in with GitHub';
    }
}

signInButton.addEventListener('click', beginSignIn);

document.getElementById('text-transcript').addEventListener('submit', async (event) => {
    event.preventDefault();

    if (!isSignedIn) {
        showError('Please sign in with GitHub to submit a transcript.');
        await beginSignIn();
        return;
    }
    const transcriptText = document.getElementById('transcript').value;
    if (!transcriptText.trim()) {
        showError('Please add your transcript first.');
        return;
    }
    const formData = {
        text: transcriptText
    }

    resultArea.innerText = 'Processing transcript...';
    showStatus('Processing transcript...');
    textSubmitButton.disabled = true
    fileSubmitButton.disabled = true
    try {
        const response = await window.api.submitTextTranscript(formData);
        handleTranscriptSubmission(response.result, response.summary)
    } catch (err) {
        showError(`Error: ${err.message}`);
    }

    textSubmitButton.disabled = false
    fileSubmitButton.disabled = false
})

document.getElementById('file-transcript').addEventListener('submit', async (event) => {
    event.preventDefault();

    if (!isSignedIn) {
        showError('Please sign in with GitHub to submit a transcript.');
        await beginSignIn();
        return;
    }
    const file = document.getElementById('file').files[0];
    if (!file) {
        showError('Please choose a transcript file first.');
        return;
    }

    resultArea.innerText = 'Processing transcript...';
    showStatus('Processing transcript...');
    textSubmitButton.disabled = true
    fileSubmitButton.disabled = true
    
    const reader = new FileReader();
    reader.onload = async () => {
        const base64 = reader.result.split(',')[1];
        try {
            const response = await window.api.submitFileTranscript({ 
                filename: file.name, 
                content: base64 
            });
            handleTranscriptSubmission(response.result, response.summary);
        } catch (err) {
            showError(`Error: ${err.message}`);
        }
        textSubmitButton.disabled = false
        fileSubmitButton.disabled = false
    };
    reader.onerror = () => {
        showError('Failed to read file.');
        textSubmitButton.disabled = false
        fileSubmitButton.disabled = false
    };
    reader.readAsDataURL(file);
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

function hideElementById(id) {
    const element = document.getElementById(id);
    element.classList.add("d-none");
}
function showElementById(id) {
    const element = document.getElementById(id);
    element.classList.remove("d-none");
}

async function proposedIssueReview(proposedIssue) {

    return new Promise((resolve) => {

        const issueTitle = document.getElementById('issue-title');
        const issueDescription = document.getElementById('issue-description');
        const issueType = document.getElementById('issue-labels');
        const issueTags = document.getElementById('issue-tags');
        const issuePriority = document.getElementById('issue-priority');
        const issueAssignee = document.getElementById('issue-assignee');
        const issueAssigneeConfidence = document.getElementById('issue-assignee-confidence');
        const issueSuggestedRepo = document.getElementById('issue-suggested-repo');
        const issueSourceExcerpt = document.getElementById('issue-source-excerpt');
        const issueStatus = document.getElementById('issue-status');
        const repoOwnerInput = document.getElementById('repo-owner');
        const repoNameInput = document.getElementById('repo-name');
        const repoRequiredWarning = document.getElementById('repo-required-warning');
        const acceptButton = document.getElementById('accept-issue');
        const declineButton = document.getElementById('decline-issue');

        repoRequiredWarning.classList.add('d-none');
        if (!proposedIssue.suggested_repo && !repoOwnerInput.value && !repoNameInput.value && lastRepoOwner && lastRepoName) {
            repoOwnerInput.value = lastRepoOwner;
            repoNameInput.value = lastRepoName;
        }

        issueTitle.value = proposedIssue.title;
        issueDescription.value = proposedIssue.description;
        issueType.value = proposedIssue.type;
        issueTags.value = proposedIssue.tags.join(', ');
        issuePriority.value = proposedIssue.priority;
        issueAssignee.value = proposedIssue.assignee;
        issueAssigneeConfidence.innerText = proposedIssue.assignee_confidence;
        issueSuggestedRepo.innerText = proposedIssue.suggested_repo;
        issueSourceExcerpt.innerText = proposedIssue.source_excerpt;
        issueStatus.innerText = proposedIssue.status;

        acceptButton.onclick = () => {
            if (!repoOwnerInput.value.trim() || !repoNameInput.value.trim()) {
                repoRequiredWarning.classList.remove('d-none');
                return;
            }

            lastRepoOwner = repoOwnerInput.value;
            lastRepoName = repoNameInput.value;

            resolve({
                title: issueTitle.value,
                description: issueDescription.value,
                type: issueType.value,
                tags: issueTags.value.split(', ').map((s) => s.trim()).filter((s) => s),
                priority: issuePriority.value,
                assignee: issueAssignee.value,
                assigneeConfidence: proposedIssue.assignee_confidence,
                suggestedRepo: proposedIssue.suggested_repo,
                sourceExcerpt: proposedIssue.source_excerpt,
                status: "accepted",
                repoOwner: repoOwnerInput.value,
                repoName: repoNameInput.value
            });
        }

        declineButton.onclick = () => {
            if (repoOwnerInput.value.trim() && repoNameInput.value.trim()) {
                lastRepoOwner = repoOwnerInput.value;
                lastRepoName = repoNameInput.value;
            }
            resolve(null);
        }
    })
}

function priorityBadgeClass(priority) {
    switch ((priority || '').toLowerCase()) {
        case 'high': return 'text-bg-danger';
        case 'medium': return 'text-bg-warning';
        case 'low': return 'text-bg-secondary';
        default: return 'text-bg-light';
    }
}

function populateAcceptedIssueSummary(acceptedIssues, summaryText) {
    console.log("Populating accepted issue summary with issues:", acceptedIssues);
    
    const formattedSummary = summaryText ? summaryText.replace(/\n/g, '<br>') : 'No summary generated.';
    
    let summaryContent = `
        <div class="app-summary-header mb-4">
            <h3 class="mb-1">Meeting Summary</h3>
            <p class="text-muted mb-4" style="line-height: 1.6;">${formattedSummary}</p>
            <h3 class="mb-1 mt-5">Accepted Issues Summary</h3>
            <p class="text-muted mb-0">The following issues have been accepted:</p>
        </div>
        <div class="accordion app-accordion" id="accepted-issues-accordion">
    `;
    for (const [index, issue] of acceptedIssues.entries()) {
        const repoLabel = (issue.repoOwner && issue.repoName)
            ? `${issue.repoOwner}/${issue.repoName}`
            : (issue.suggestedRepo || '—');
        summaryContent += `
            <div class="accordion-item app-accordion-item">
                <h2 class="accordion-header">
                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-${index}" aria-expanded="false" aria-controls="collapse-${index}">
                    <span class="app-accordion-title">
                        <span class="app-accordion-title-text">${issue.title}</span>
                        <span class="badge ${priorityBadgeClass(issue.priority)} app-accordion-badge">${issue.priority || 'No priority'}</span>
                    </span>
                </button>
                </h2>
                <div id="collapse-${index}" class="accordion-collapse collapse">
                    <div class="accordion-body">
                        <dl class="app-meta-grid">
                            <div class="app-meta-cell app-meta-cell-full"><dt>Title</dt><dd>${issue.title}</dd></div>
                            <div class="app-meta-cell app-meta-cell-full"><dt>Description</dt><dd>${issue.description}</dd></div>
                            <div class="app-meta-cell app-meta-cell-full"><dt>Repository</dt><dd>${repoLabel}</dd></div>
                            <div class="app-meta-cell"><dt>Type</dt><dd>${issue.type || '—'}</dd></div>
                            <div class="app-meta-cell"><dt>Assignee</dt><dd>${issue.assignee || 'Unassigned'}</dd></div>
                            <div class="app-meta-cell"><dt>Assignee Confidence</dt><dd>${issue.assigneeConfidence ?? '—'}</dd></div>
                            <div class="app-meta-cell"><dt>Status</dt><dd><span class="badge text-bg-success text-uppercase">${issue.status || '—'}</span></dd></div>
                            <div class="app-meta-cell app-meta-cell-full"><dt>Tags</dt><dd>${(issue.tags && issue.tags.length) ? issue.tags.map((t) => `<span class="badge text-bg-light app-tag">${t}</span>`).join(' ') : '—'}</dd></div>
                            <div class="app-meta-cell app-meta-cell-full"><dt>Source Excerpt</dt><dd class="app-source-excerpt">${issue.sourceExcerpt || '—'}</dd></div>
                        </dl>
                    </div>
                </div>
            </div>`;
    }
    summaryContent += `
    </div>
    <div class="mt-4 d-flex justify-content-between">
        <button id="cancel-button" class="btn btn-outline-secondary px-4">Cancel</button>
        <button id="finish-button" class="btn btn-primary px-4">Finish</button>
    </div>`;
    document.getElementById('transcript-summary').innerHTML = summaryContent;

    const accordion = document.getElementById('accepted-issues-accordion');
    const buttons = accordion.querySelectorAll('.accordion-button');
    buttons.forEach((button) => {
        button.addEventListener('click', () => {
            const target = document.querySelector(button.getAttribute('data-bs-target'));
            const isOpen = target.classList.contains('show');

            buttons.forEach((otherButton) => {
                const otherTarget = document.querySelector(otherButton.getAttribute('data-bs-target'));
                otherTarget.classList.remove('show');
                otherButton.classList.add('collapsed');
                otherButton.setAttribute('aria-expanded', 'false');
            });

            if (!isOpen) {
                target.classList.add('show');
                button.classList.remove('collapsed');
                button.setAttribute('aria-expanded', 'true');
            }
        });
    });
}

async function acceptIssues() {
    return new Promise(async (resolve) => {
        const finishButton = document.getElementById('finish-button');
        const cancelButton = document.getElementById('cancel-button');

        finishButton.onclick = async () => {
            resolve(true);
        }

        cancelButton.onclick = async () => {
            resolve(false);
        }
    })
}

async function handleTranscriptSubmission(issueResult, summaryText) {
    hideElementById('transcript-submission');
    showElementById('issue-review');
    currentTab.innerText = 'Issue Review';
    let acceptedIssues = [];
    for (const proposedIssue of JSON.parse(issueResult)) {
        const issueResponse = await proposedIssueReview(proposedIssue);
        if (issueResponse) {
            acceptedIssues.push(issueResponse);
        }
        else {
            console.log(`Issue "${proposedIssue.title}" was declined.`);
        }
    }
    hideElementById('issue-review');
    showElementById('transcript-summary');
    currentTab.innerText = 'Transcript Summary';
    populateAcceptedIssueSummary(acceptedIssues, summaryText);

    const submitIssues = await acceptIssues()
    hideElementById('transcript-summary');
    showElementById('transcript-submission');
    currentTab.innerText = 'Transcript Submission';
    if (submitIssues) {
        const submissionResult = await window.api.submitAcceptedIssues(acceptedIssues);
        if (submissionResult.status === 'success') {
            console.log('Accepted issues submitted successfully.');
            resultArea.innerText = 'Accepted issues submitted successfully.';
            resultMessage = createIssueSubmissionResults(submissionResult.result)
            showStatus('Accepted issues successfully processed.');
            submissionResults.innerHTML = resultMessage
        }  else {
            console.error('Failed to submit accepted issues:', submitIssues.error);
            resultArea.innerText = `Failed to submit accepted issues: ${submitIssues.error}`;
            showError(`Failed to submit accepted issues: ${submitIssues.error}`);
        }
    } else {
        resultArea.innerText = 'Accepted issues submission canceled by user.';
        showStatus('Accepted issues submission canceled by user.');
    }
}
