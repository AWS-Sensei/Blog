---
title: "What Does This Blog Cost? — A Live Cost Dashboard with AWS Cost Explorer"
date: 2026-04-14T00:00:00+02:00
lastmod: 2026-04-14T00:00:00+02:00
draft: false
author: "Marcel"
description: "How I display my blog's monthly AWS costs directly in the blog — using Cost Explorer, Lambda, EventBridge and a Hugo shortcode."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Cost Explorer", "Lambda", "EventBridge", "FinOps", "SAM", "Hugo", "Serverless"]
lightgallery: true
---

One question I ask myself with every AWS project: what does this actually cost? For this blog I built the answer directly in — at the bottom of this post you can see live what aws-sensei.cloud has cost in the current month, broken down by AWS service.

## The Idea

The goal was not a static screenshot dashboard, but real live data straight from AWS — updated daily, embedded directly in the blog. A Hugo shortcode, one API call, done.

The data source is **AWS Cost Explorer**, which provides accurate cost data per service. The problem: Cost Explorer charges $0.01 per API call — too expensive for every page view. The solution is caching via **SSM Parameter Store**.

## The Architecture

```text
EventBridge (daily 06:00 UTC)
    → Lambda refresh → Cost Explorer API → SSM Parameter Store
                                                    ↓
Browser → API Gateway → Lambda read → SSM Parameter Store
```

Two Lambdas, clearly separated responsibilities:

- **sensei-cost-refresh** — triggered daily by EventBridge, queries Cost Explorer and writes the result as JSON to SSM Parameter Store
- **sensei-cost-read** — triggered on every widget call, reads from SSM only — no Cost Explorer call, no additional costs

## The SAM Template

Both Lambdas live in the same stack but in separate subdirectories so SAM packages them individually:

```text
apis/cost/
├── src/
│   ├── read/handler.py
│   └── refresh/handler.py
└── template.yaml
```

The EventBridge trigger is defined directly in the SAM template as a `Schedule` event:

```yaml
CostRefreshFunction:
  Type: AWS::Serverless::Function
  Properties:
    FunctionName: sensei-cost-refresh
    Handler: handler.lambda_handler
    CodeUri: src/refresh/
    Events:
      DailyRefresh:
        Type: Schedule
        Properties:
          Schedule: cron(0 6 * * ? *)
          Name: sensei-cost-refresh-daily
```

No separate EventBridge template, no manual configuration — everything in one file.

## The Refresh Lambda

```python
ce = boto3.client("ce", region_name="us-east-1")
ssm = boto3.client("ssm", region_name="eu-central-1")

def lambda_handler(event, context):
    today = date.today()
    start = today.replace(day=1).isoformat()
    end = today.isoformat()

    response = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    services = {}
    total = 0.0
    for group in response["ResultsByTime"][0]["Groups"]:
        service = group["Keys"][0]
        amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
        if amount >= 0.0001:
            services[service] = round(amount, 4)
            total += amount

    ssm.put_parameter(
        Name="/sensei/blog/cost-data",
        Value=json.dumps({
            "total": round(total, 4),
            "services": services,
            "period": {"start": start, "end": end},
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
        }),
        Type="String",
        Overwrite=True,
    )
```

One important note: **Cost Explorer is only available in `us-east-1`** — the boto3 client must set this explicitly, regardless of which region the Lambda runs in. The SSM client stays in `eu-central-1`.

## IAM Permissions

The refresh Lambda needs two permissions:

```yaml
- ce:GetCostAndUsage   # query Cost Explorer
- ssm:PutParameter     # write result to SSM
```

The read Lambda only one:

```yaml
- ssm:GetParameter     # read cache from SSM
```

No wildcard, no `*` on actions — least privilege as always.

## The Widget

The Hugo shortcode calls the read Lambda via API Gateway and renders the results as a list sorted by cost. If the SSM parameter is not yet populated (e.g. right after the first deployment), the widget shows a notice instead of an error.

In Markdown all it takes is:

```markdown
{{</* cost */>}}
```

## Running Costs

{{< cost >}}
