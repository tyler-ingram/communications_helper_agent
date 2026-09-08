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
cd communications_helper_agent
cd backend
uv sync
lms get qwen/qwen3-4b-2507
cd ../frontend
npm install
```

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

No other configuration is required to run the service locally.

## Running the code
To run the backend lms server to enable model calls use:
```bash
 lms daemon up
 lms server start
```
To run a python file:
```bash 
uv run <file_name>
```
To start the frontend application:
```bash
#In communcications_helper_agent/frontend
npm start
```
---