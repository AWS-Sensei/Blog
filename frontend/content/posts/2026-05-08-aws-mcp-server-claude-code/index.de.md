---
title: "AWS MCP Server mit Claude Code"
date: 2026-05-08T00:00:00+02:00
lastmod: 2026-05-08T00:00:00+02:00
draft: false
author: "Marcel"
description: "Wie man den AWS MCP Server in zwei Befehlen mit Claude Code verbindet — und warum Frankfurt der bessere Endpoint für europäische Workloads ist."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Claude Code", "MCP", "AI", "Developer Tools"]
lightgallery: true
---

AWS hat kürzlich die [General Availability des AWS MCP Servers](https://aws.amazon.com/de/blogs/aws/the-aws-mcp-server-is-now-generally-available/) angekündigt. Er gibt KI-Coding-Assistenten wie Claude Code direkten Zugriff auf über 15.000 AWS-API-Operationen, aktuelle Dokumentation und sandboxed Script-Ausführung — alles über das Model Context Protocol.

Ich habe es für meinen eigenen Workflow eingerichtet und bin dabei über einige Stolpersteine gestolpert. Hier ist die kurze Version von dem, was tatsächlich funktioniert.

---

## Was ist der AWS MCP Server?

MCP (Model Context Protocol) ist ein Standard, der KI-Assistenten ermöglicht, externe Tools aufzurufen. Der AWS MCP Server fungiert als Proxy zwischen dem KI-Assistenten und AWS — er übernimmt die SigV4-Authentifizierung und leitet Anfragen an die richtigen Services weiter.

Mit der Verbindung kann ich Claude Code Dinge fragen wie "Welche Lambda-Funktionen sind in eu-central-1 deployed?" — und bekomme eine echte Antwort.

---

## Voraussetzungen

- **Claude Code** installiert — verfügbar unter [claude.ai/code](https://claude.ai/code)
- **uv** installiert — der Python-Paketmanager, der den Proxy ausführt

**Windows (winget):**

```bash
winget install astral-sh.uv --accept-source-agreements --accept-package-agreements
```

**macOS/Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

- AWS Credentials lokal konfiguriert (`~/.aws/credentials` oder Umgebungsvariablen)

---

## Setup

Terminal öffnen (Git Bash, PowerShell, oder beliebige Shell) und ausführen:

**US East (N. Virginia):**

```bash
claude mcp add-json aws-mcp --scope user \
  '{"command":"uvx","args":["mcp-proxy-for-aws@latest","https://aws-mcp.us-east-1.api.aws/mcp","--metadata","AWS_REGION=us-east-1"]}'
```

**Europa (Frankfurt) — empfohlen für EU-Workloads:**

```bash
claude mcp add-json aws-mcp --scope user \
  '{"command":"uvx","args":["mcp-proxy-for-aws@latest","https://aws-mcp.eu-central-1.api.aws/mcp","--metadata","AWS_REGION=eu-central-1"]}'
```

Das `--scope user` Flag speichert den Server global, sodass er in allen Projekten verfügbar ist.

---

## Überprüfung

In Claude Code `/mcp` eingeben — der `aws-mcp` Server sollte als verbunden erscheinen. Bei der VS Code Extension: VS Code neu starten und erneut `/mcp` prüfen.

Das war's.

---

## Was man damit machen kann

Ein paar Dinge, die ich getestet habe:

- Deployed Lambda-Funktionen und deren Konfigurationen auflisten
- CloudFormation Stack Outputs abfragen
- AWS-Dokumentation durchsuchen, ohne den Editor zu verlassen
- Sandboxed Python-Skripte gegen AWS-APIs ausführen

Das `call_aws`-Tool deckt alle 15.000+ AWS-API-Operationen ab. Alles, was mit der AWS CLI möglich ist, kann man jetzt auch Claude Code fragen.

---

{{< chat >}}
