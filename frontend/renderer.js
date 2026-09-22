const signInButton = document.getElementById('github-signin');
const authStatus = document.getElementById('auth-status');
const resultArea = document.getElementById('result-area');
const currentTab = document.getElementById('current-tab');
const fileSubmitButton = document.getElementById('file-transcript')
const textSubmitButton = document.getElementById('text-transcript')

function setAuthStatus(status) {
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

signInButton.addEventListener('click', async () => {
    signInButton.disabled = true;
    signInButton.innerText = 'Waiting for GitHub authorization...';
    try {
        await window.api.signInWithGithub();
        await refreshAuthStatus();
    } catch (err) {
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
    textSubmitButton.disabled = true
    fileSubmitButton.disabled = true
    try {
        const response = await window.api.submitTextTranscript(formData);
        handleTranscriptSubmission(response)
    } catch (err) {
        resultArea.innerText = `Error: ${err.message}`;
    }

    textSubmitButton.disabled = false
    fileSubmitButton.disabled = false
})

document.getElementById('file-transcript').addEventListener('submit', async (event) => {
    event.preventDefault();

    const file = document.getElementById('file').files[0];
    if (!file) return;

    resultArea.innerText = 'Processing transcript...';
    textSubmitButton.disabled = true
    fileSubmitButton.disabled = true
    try {
        const text = await file.text();
        const response = await window.api.submitFileTranscript({ file: text });
        handleTranscriptSubmission(response)
    } catch (err) {
        resultArea.innerText = `Error: ${err.message}`;
    }
    textSubmitButton.disabled = false
    fileSubmitButton.disabled = false
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
        const acceptButton = document.getElementById('accept-issue');
        const declineButton = document.getElementById('decline-issue');

        issueTitle.value = proposedIssue.title;
        issueDescription.value = proposedIssue.description;
        issueType.value = proposedIssue.type;
        issueTags.value = proposedIssue.tags.join(', ');
        issuePriority.value = proposedIssue.priority;
        issueAssignee.value = proposedIssue.assignee;
        issueAssigneeConfidence.innerText = proposedIssue.assigne_confidence;
        issueSuggestedRepo.innerText = proposedIssue.suggested_repo;
        issueSourceExcerpt.innerText = proposedIssue.source_excerpt;
        issueStatus.innerText = proposedIssue.status;

        acceptButton.onclick = () => {
            resolve({
                title: issueTitle.value,
                description: issueDescription.value,
                type: issueType.value,
                tags: issueTags.value.split(', ').map((s) => s.trim()).filter((s) => s),
                priority: issuePriority.value,
                assignee: issueAssignee.value,
                assigneeConfidence: proposedIssue.assigneeConfidence,
                suggestedRepo: proposedIssue.suggestedRepo,
                sourceExcerpt: proposedIssue.sourceExcerpt,
                status: "accepted",
                repoOwner: repoOwnerInput.value,
                repoName: repoNameInput.value
            });
        }

        declineButton.onclick = () => {
            resolve(null);
        }
    })
}

function populateAcceptedIssueSummary(acceptedIssues) {
    console.log("Populating accepted issue summary with issues:", acceptedIssues);
    let summaryContent = `
        <h3>Accepted Issues Summary</h3>
        <p>The following issues have been accepted:</p>
        <div class="accordion" id="accepted-issues-accordion">
    `;
    for (const [index, issue] of acceptedIssues.entries()) {
        summaryContent += `
            <div class="accordion-item">
                <h2 class="accordion-header">
                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-${index}" aria-expanded="false" aria-controls="collapse-${index}">
                ${issue.title}
                </button>
                </h2>
                <div id="collapse-${index}" class="accordion-collapse collapse">
                    <div class="accordion-body">
                        <p><strong>Description:</strong> ${issue.description}</p>
                        <p><strong>Type:</strong> ${issue.type}</p>
                        <p><strong>Tags:</strong> ${issue.tags.join(', ')}</p>
                        <p><strong>Priority:</strong> ${issue.priority}</p>
                        <p><strong>Assignee:</strong> ${issue.assignee}</p>
                    </div>
                </div>
            </div>`;
    }
    summaryContent += `
    </div>
    <div class="mt-3 d-flex justify-content-between">
    <button id="cancel-button" class="btn btn-secondary mt-3 w-25">Cancel</button>
    <button id="finish-button" class="btn btn-primary mt-3 w-25">Finish</button>
    </div>`;
    document.getElementById('transcript-summary').innerHTML = summaryContent;
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

async function handleTranscriptSubmission(response) {
    hideElementById('transcript-submission');
    showElementById('issue-review');
    currentTab.innerText = 'Issue Review';
    let acceptedIssues = [];
    for (const proposedIssue of JSON.parse(response.result)) {
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
    populateAcceptedIssueSummary(acceptedIssues);


    const submitIssues = await acceptIssues()
    hideElementById('transcript-summary');
    showElementById('transcript-submission');
    currentTab.innerText = 'Transcript Submission';
    if (submitIssues) {
        const submissionResult = await window.api.submitAcceptedIssues(acceptedIssues);
        if (submissionResult.status === 'success') {
            console.log('Accepted issues submitted successfully.');
            resultArea.innerText = 'Accepted issues submitted successfully.';
        }  else {
            console.error('Failed to submit accepted issues:', submitIssues.error);
            resultArea.innerText = `Failed to submit accepted issues: ${submitIssues.error}`;
        }
    } else {
        resultArea.innerText = 'Accepted issues submission canceled by user.';
    }
}