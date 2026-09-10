# communications-helper-agent

A agent for helping organize unstructured team communications into useful data. 
---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Environment Configuration](#environment-configuration)

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

No other configuration is required to run the service locally.

## Running the code
To start the application use the following script
```bash
# In communications_helper_agent/frontend
npm run start
```
---