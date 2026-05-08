---
title: "AWS MCP Server with Claude Code"
date: 2026-05-08T00:00:00+02:00
lastmod: 2026-05-08T00:00:00+02:00
draft: false
author: "Marcel"
description: "How to connect the AWS MCP Server to Claude Code in two commands — and why Frankfurt is the better endpoint for European workloads."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Claude Code", "MCP", "AI", "Developer Tools"]
lightgallery: true
---

AWS recently announced the [general availability of the AWS MCP Server](https://aws.amazon.com/de/blogs/aws/the-aws-mcp-server-is-now-generally-available/). It gives AI coding assistants like Claude Code direct access to over 15,000 AWS API operations, live documentation, and sandboxed script execution — all via the Model Context Protocol.

I set it up for my own workflow and ran into a few stumbling blocks. Here's the short version of what actually works.

---

## What is the AWS MCP Server?

MCP (Model Context Protocol) is a standard that lets AI assistants call external tools. The AWS MCP Server acts as a proxy between your AI assistant and AWS — handling SigV4 authentication and routing requests to the right services.

With it connected, I can ask Claude Code things like "what Lambda functions are deployed in eu-central-1?" and get a real answer, not a hallucinated one.

---

## Prerequisites

- **Claude Code** installed — get it at [claude.ai/code](https://claude.ai/code)
- **uv** installed — the Python package manager that runs the proxy

**Windows (winget):**

```bash
winget install astral-sh.uv --accept-source-agreements --accept-package-agreements
```

**macOS/Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

- AWS credentials configured locally (`~/.aws/credentials` or environment variables)

---

## Setup

Open a terminal (Git Bash, PowerShell, or any shell) and run:

**US East (N. Virginia):**

```bash
claude mcp add-json aws-mcp --scope user \
  '{"command":"uvx","args":["mcp-proxy-for-aws@latest","https://aws-mcp.us-east-1.api.aws/mcp","--metadata","AWS_REGION=us-east-1"]}'
```

**Europe (Frankfurt) — recommended for EU workloads:**

```bash
claude mcp add-json aws-mcp --scope user \
  '{"command":"uvx","args":["mcp-proxy-for-aws@latest","https://aws-mcp.eu-central-1.api.aws/mcp","--metadata","AWS_REGION=eu-central-1"]}'
```

The `--scope user` flag saves the server globally, so it's available across all your projects.

---

## Verify

In Claude Code, type `/mcp` — the `aws-mcp` server should appear as connected. If you're using the VS Code extension, restart VS Code and check `/mcp` again.

That's it.

---

## What you can do with it

A few things I've tested:

- List deployed Lambda functions and their configurations
- Query CloudFormation stack outputs
- Search AWS documentation without leaving the editor
- Run sandboxed Python scripts against AWS APIs

The `call_aws` tool covers all 15,000+ AWS API operations. If you can do it with the AWS CLI, you can now ask Claude Code to do it instead.

---

{{< chat >}}
