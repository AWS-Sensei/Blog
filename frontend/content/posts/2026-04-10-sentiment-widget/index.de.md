---
title: "Sentiment-Analyse direkt im Blog — mit AWS Comprehend, Lambda und API Gateway"
date: 2026-04-10T00:00:00+02:00
lastmod: 2026-04-10T00:00:00+02:00
draft: false
author: "Marcel"
description: "Wie ich ein interaktives Sentiment-Analyse Widget in meinen Blog eingebaut habe — Lambda, API Gateway, AWS Comprehend und ein Hugo Shortcode."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Lambda", "API Gateway", "Comprehend", "SAM", "Hugo", "Serverless"]
lightgallery: true
---

{{< listen >}}

Die APIs-Pipeline aus dem [vorherigen Post](/de/posts/2026-04-02-three-pipelines-one-platform/) stand bereit — sie wartete auf ihr erstes Feature. Das Ergebnis ist das Sentiment-Analyse Widget, das du am Ende dieses Posts ausprobieren kannst: Einen Satz eingeben, AWS Comprehend analysiert ihn in Echtzeit und zeigt ob er positiv, negativ, neutral oder gemischt klingt.

## Die Architektur

```text
Browser → API Gateway → Lambda → AWS Comprehend
```

Drei AWS-Services, alle serverless. Kein Server, keine Infrastruktur die gewartet werden muss — nur Code und Konfiguration.

**AWS Comprehend** ist ein managed NLP-Service von AWS. Er erkennt Sprache, extrahiert Entitäten, analysiert Stimmung. Für `DetectSentiment` schickst du einen Text rein und bekommst vier Wahrscheinlichkeitswerte zurück: `POSITIVE`, `NEGATIVE`, `NEUTRAL` und `MIXED` — jeweils zwischen 0 und 1, zusammen immer 1.

## Das SAM-Template

Jedes API-Feature bekommt seinen eigenen Ordner unter `apis/`:

```text
apis/sentiment/
├── src/
│   ├── handler.py
│   └── requirements.txt
└── template.yaml
```

Der Code liegt in `src/` damit SAM nur den Handler verpackt und `template.yaml` nicht mit in die Lambda landet.

Das SAM-Template definiert die Lambda-Funktion und das API Gateway in einem:

```yaml
SentimentFunction:
  Type: AWS::Serverless::Function
  Properties:
    FunctionName: sensei-sentiment
    Handler: handler.lambda_handler
    CodeUri: src/
    Policies:
      - Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Action:
              - comprehend:DetectSentiment
            Resource: "*"
    Events:
      SentimentPost:
        Type: Api
        Properties:
          RestApiId: !Ref SentimentApi
          Path: /sentiment
          Method: POST
```

Die Lambda-Funktion bekommt nur eine einzige IAM-Permission: `comprehend:DetectSentiment`. Kein Wildcard, kein `*` auf Actions — nur genau was gebraucht wird.

## Der Lambda-Handler

```python
import json
import boto3

comprehend = boto3.client("comprehend", region_name="eu-central-1")

def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}")
    text = body.get("text", "").strip()

    result = comprehend.detect_sentiment(Text=text, LanguageCode="en")

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "sentiment": result["Sentiment"].lower(),
            "scores": {
                "positive": round(result["SentimentScore"]["Positive"], 4),
                "negative": round(result["SentimentScore"]["Negative"], 4),
                "neutral":  round(result["SentimentScore"]["Neutral"],  4),
                "mixed":    round(result["SentimentScore"]["Mixed"],    4),
            }
        })
    }
```

boto3 ist im Lambda-Runtime bereits enthalten — `requirements.txt` ist leer, keine externen Dependencies nötig.

## CORS

Das Widget läuft im Browser und ruft eine andere Domain auf (API Gateway). Ohne CORS-Header blockiert der Browser die Antwort. Der Handler gibt bei jedem Response diese Header mit:

```python
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "https://aws-sensei.cloud",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}
```

Zusätzlich antwortet die Lambda auf `OPTIONS`-Requests direkt mit 200 — das ist der Browser-Preflight den er vor jedem Cross-Origin-POST schickt.

## Throttling

AWS Comprehend kostet pro API-Aufruf. Um unkontrollierte Kosten zu vermeiden, ist im API Gateway ein Rate-Limit gesetzt:

```yaml
MethodSettings:
  - ResourcePath: "/*"
    HttpMethod: "*"
    ThrottlingRateLimit: 1
    ThrottlingBurstLimit: 5
```

1 Request pro Sekunde, Burst bis 5. Bei Überschreitung antwortet API Gateway automatisch mit `429 Too Many Requests` — ohne dass Lambda oder Comprehend überhaupt aufgerufen werden.

## Der Hugo Shortcode

Damit das Widget in jeden Blog Post eingebettet werden kann, gibt es einen Hugo Shortcode unter `frontend/layouts/shortcodes/sentiment.html`. Im Markdown reicht dann:

```markdown
{{</* sentiment */>}}
```

Der Shortcode enthält das komplette HTML, CSS und JavaScript — kein externes Framework, kein Build-Step. Ein `fetch()` auf die API Gateway URL, Ergebnis parsen, Balken rendern.

## Das Deployment

Die APIs-Pipeline aus dem letzten Post erledigt das Deployment automatisch. Wenn sich etwas unter `apis/**` ändert, triggert die Pipeline und SAM deployed alle Stacks:

```bash
for template in apis/*/template.yaml; do
  stack_name="sensei-api-$(basename $(dirname $template))"
  sam deploy --template-file $template --stack-name $stack_name ...
done
```

Neues Feature = neuer Ordner. Die Pipeline muss nie angefasst werden.

## Ausprobieren

{{< sentiment >}}

---

{{< chat >}}
