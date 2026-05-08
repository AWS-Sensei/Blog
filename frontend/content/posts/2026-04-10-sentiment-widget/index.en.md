---
title: "Sentiment Analysis in the Blog — with AWS Comprehend, Lambda and API Gateway"
date: 2026-04-10T00:00:00+02:00
lastmod: 2026-04-10T00:00:00+02:00
draft: false
author: "Marcel"
description: "How I built an interactive sentiment analysis widget into my blog — Lambda, API Gateway, AWS Comprehend and a Hugo shortcode."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Lambda", "API Gateway", "Comprehend", "SAM", "Hugo", "Serverless"]
lightgallery: true
---

{{< listen >}}

The APIs pipeline from the [previous post](/posts/2026-04-02-three-pipelines-one-platform/) was ready — waiting for its first feature. The result is the sentiment analysis widget you can try out at the bottom of this post: type a sentence, AWS Comprehend analyzes it in real time and tells you whether it reads as positive, negative, neutral, or mixed.

## The Architecture

```text
Browser → API Gateway → Lambda → AWS Comprehend
```

Three AWS services, all serverless. No server, no infrastructure to maintain — just code and configuration.

**AWS Comprehend** is a managed NLP service from AWS. It detects language, extracts entities, and analyzes sentiment. For `DetectSentiment` you send in a text and get back four probability scores: `POSITIVE`, `NEGATIVE`, `NEUTRAL`, and `MIXED` — each between 0 and 1, always summing to 1.

## The SAM Template

Each API feature gets its own folder under `apis/`:

```text
apis/sentiment/
├── src/
│   ├── handler.py
│   └── requirements.txt
└── template.yaml
```

The code lives in `src/` so SAM only packages the handler and `template.yaml` doesn't end up inside the Lambda.

The SAM template defines the Lambda function and the API Gateway in one:

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

The Lambda function gets exactly one IAM permission: `comprehend:DetectSentiment`. No wildcard, no `*` on actions — only what's actually needed.

## The Lambda Handler

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

boto3 is already included in the Lambda runtime — `requirements.txt` is empty, no external dependencies needed.

## CORS

The widget runs in the browser and calls a different domain (API Gateway). Without CORS headers the browser blocks the response. The handler includes these headers on every response:

```python
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "https://aws-sensei.cloud",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}
```

In addition, the Lambda responds to `OPTIONS` requests directly with 200 — that's the browser preflight it sends before every cross-origin POST.

## Throttling

AWS Comprehend charges per API call. To prevent runaway costs, the API Gateway has a rate limit configured:

```yaml
MethodSettings:
  - ResourcePath: "/*"
    HttpMethod: "*"
    ThrottlingRateLimit: 1
    ThrottlingBurstLimit: 5
```

1 request per second, burst up to 5. When exceeded, API Gateway automatically responds with `429 Too Many Requests` — without Lambda or Comprehend ever being invoked.

## The Hugo Shortcode

To embed the widget in any blog post, there's a Hugo shortcode at `frontend/layouts/shortcodes/sentiment.html`. In Markdown all it takes is:

```markdown
{{</* sentiment */>}}
```

The shortcode contains the complete HTML, CSS and JavaScript — no external framework, no build step. A `fetch()` to the API Gateway URL, parse the result, render the bars.

## The Deployment

The APIs pipeline from the last post handles deployment automatically. Whenever something changes under `apis/**`, the pipeline triggers and SAM deploys all stacks:

```bash
for template in apis/*/template.yaml; do
  stack_name="sensei-api-$(basename $(dirname $template))"
  sam deploy --template-file $template --stack-name $stack_name ...
done
```

New feature = new folder. The pipeline never needs to be touched.

## Try It Out

{{< sentiment >}}

---

{{< chat >}}
