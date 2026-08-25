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
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- A Claude API key

---

## Setup

Clone the repo and install dependencies:

```bash
git clone https://github.com/tyler-ingram/communications_helper_agent.git
cd communications_helper_agent
uv sync
```

---

## Environment Configuration

Copy the example env file and add your Claude key:

```bash
cp .env.example .env
```

`.env.example`:

```env
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_KEY_HERE
```

No other configuration is required to run the service locally.

---