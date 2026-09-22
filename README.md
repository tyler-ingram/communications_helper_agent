# communications-helper-agent

A agent for helping organize unstructured team communications into useful data. 
---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Environment Configuration](#environment-configuration)
- [GitHub OAuth App Setup](#github-oauth-app-setup)

---

## Overview

TODO
---

## Prerequisites

- Python 3.13+
- Node.js 11.6.2+
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Install LM Studio [from https://lmstudio.ai/](https://lmstudio.ai/docs/developer/core/headless)

---

## Setup

Clone the repo and install dependencies:

```bash
git clone https://github.com/tyler-ingram/communications_helper_agent.git
cd communications_helper_agent/frontend
npm run setup
```
By default, the setup script will retrieve and download qwen/qwen3-4b-2507 for the LLM. This model is approximately 2.5 GB large.

To get another model:
```bash
lms get <model_name>
```
---

## Environment Configuration

Copy the example env file:

```bash
cp .env.example .env
```
If a different model is chosen during setup, ensure that the .env file states which model you want to use in the LM_MODEL field.

To use the "Sign in with GitHub" flow, you'll also need a GitHub OAuth App — see [GitHub OAuth App Setup](#github-oauth-app-setup) below.

## GitHub OAuth App Setup

The app signs in to GitHub via OAuth rather than a shared token, so each developer should register their **own** GitHub OAuth App rather than sharing one client ID/secret with teammates.

1. Go to [github.com/settings/developers](https://github.com/settings/developers) → **New OAuth App**.
2. Fill in:
   - **Application name**: anything, e.g. `Communications Helper Agent (Dev)`
   - **Homepage URL**: any valid URL, e.g. your fork/clone of this repo — not used functionally
   - **Authorization callback URL**: `commshelper://oauth/callback` (must match exactly)
3. Leave **Enable Device Flow**, **Enable Advanced Device Flow**, and **Allow wildcard matching** unchecked — this app uses the authorization-code + custom-protocol-redirect flow, not Device Flow, and wildcard matching isn't needed since the callback URL is fixed. Leaving **Expire access tokens** off keeps tokens non-expiring, matching what's currently implemented (no token-refresh logic exists yet).
4. After creating the app, copy the **Client ID**, then generate and copy a **Client Secret**.
5. Add both to your `backend/.env`:
   ```bash
   GITHUB_OAUTH_CLIENT_ID=your_client_id_here
   GITHUB_OAUTH_CLIENT_SECRET=your_client_secret_here
   ```

## Running the code
To start the application use the following script
```bash
# In communications_helper_agent/frontend
npm run start
```
---