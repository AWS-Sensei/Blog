---
title: "Was kostet dieser Blog? — Ein Live-Kosten-Dashboard mit AWS Cost Explorer"
date: 2026-04-14T00:00:00+02:00
lastmod: 2026-04-14T00:00:00+02:00
draft: false
author: "Marcel"
description: "Wie ich die monatlichen AWS-Kosten meines Blogs direkt im Blog anzeige — mit Cost Explorer, Lambda, EventBridge und einem Hugo Shortcode."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Cost Explorer", "Lambda", "EventBridge", "FinOps", "SAM", "Hugo", "Serverless"]
lightgallery: true
---

Eine Frage die ich mir bei jedem AWS-Projekt stelle: Was kostet das eigentlich? Bei diesem Blog habe ich die Antwort direkt eingebaut — am Ende dieses Posts siehst du live, was aws-sensei.cloud im laufenden Monat gekostet hat, aufgeschlüsselt nach AWS-Service.

## Die Idee

Das Ziel war kein statisches Screenshot-Dashboard, sondern echte Live-Daten direkt aus AWS — täglich aktualisiert, direkt im Blog eingebettet. Ein Hugo Shortcode, ein API-Aufruf, fertig.

Die Datenquelle ist der **AWS Cost Explorer**, der genaue Kostendaten pro Service liefert. Das Problem: Cost Explorer kostet $0,01 pro API-Aufruf — zu teuer für jeden Seitenaufruf. Die Lösung ist Caching über den **SSM Parameter Store**.

## Die Architektur

```text
EventBridge (täglich 06:00 UTC)
    → Lambda refresh → Cost Explorer API → SSM Parameter Store
                                                    ↓
Browser → API Gateway → Lambda read → SSM Parameter Store
```

Zwei Lambdas, klar getrennte Verantwortlichkeiten:

- **sensei-cost-refresh** — wird täglich von EventBridge aufgerufen, fragt Cost Explorer ab und schreibt das Ergebnis als JSON in den SSM Parameter Store
- **sensei-cost-read** — wird bei jedem Widget-Aufruf ausgelöst, liest nur aus SSM — kein Cost Explorer Call, keine zusätzlichen Kosten

## Das SAM-Template

Beide Lambdas leben im selben Stack, aber in separaten Unterordnern damit SAM sie einzeln verpackt:

```text
apis/cost/
├── src/
│   ├── read/handler.py
│   └── refresh/handler.py
└── template.yaml
```

Der EventBridge-Trigger ist direkt im SAM-Template als `Schedule`-Event definiert:

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

Kein separates EventBridge-Template, keine manuelle Konfiguration — alles in einer Datei.

## Die Refresh-Lambda

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

Ein wichtiger Hinweis: **Cost Explorer ist nur in `us-east-1` verfügbar** — der boto3-Client muss das explizit setzen, egal in welcher Region die Lambda läuft. Der SSM-Client bleibt in `eu-central-1`.

## Die IAM-Permissions

Die Refresh-Lambda braucht zwei Permissions:

```yaml
- ce:GetCostAndUsage   # Cost Explorer abfragen
- ssm:PutParameter     # Ergebnis in SSM schreiben
```

Die Read-Lambda nur eine:

```yaml
- ssm:GetParameter     # Cache aus SSM lesen
```

Kein Wildcard, kein `*` auf Actions — Least Privilege wie immer.

## Das Widget

Der Hugo Shortcode ruft die Read-Lambda über API Gateway ab und rendert die Ergebnisse als sortierte Liste nach Kosten. Ist der SSM-Parameter noch nicht befüllt (z.B. direkt nach dem ersten Deployment), zeigt das Widget einen Hinweis statt eines Fehlers.

Im Markdown reicht:

```markdown
{{</* cost */>}}
```

## Laufende Kosten

{{< cost >}}

## Kommentare

{{< chat >}}
