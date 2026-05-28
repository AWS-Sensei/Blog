---
title: "Wie ich Google Analytics durch 3 AWS-Services ersetzt habe"
date: 2026-05-18T00:00:00+02:00
lastmod: 2026-05-18T00:00:00+02:00
draft: false
author: "Marcel"
description: "Privacy-first Analytics mit CloudFront, Kinesis Firehose und Athena — kein Tracking-Cookie, kein Drittanbieter, volle Kontrolle über die Daten."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "CloudFront", "Kinesis", "Athena", "Lambda", "Analytics", "Privacy", "SAM", "Serverless"]
lightgallery: true
---

{{< listen >}}

Google Analytics ist die offensichtliche Wahl für Blog-Analytics — kostenlos, fertig, funktioniert. Aber es bedeutet auch: Drittanbieter-Cookie, Datenweitergabe an Google, und ein Banner den man irgendwie DSGVO-konform einbinden muss. Für einen Blog über AWS erschien es naheliegend, das anders zu lösen.

Das Ergebnis: Ein eigenes Analytics-System aus drei AWS-Services, das keine Cookies setzt, keine IP-Adressen speichert und DNT respektiert — mit einem live Dashboard unter [/stats](/stats/).

## Die Architektur

```text
Browser
  │  POST /track  (keepalive fetch)
  ▼
CloudFront Function  ──  Cookies strippen
  │
  ▼
API Gateway → Lambda  ──  Bot-Filter, Session-Hash, Firehose
  │
  ▼
Kinesis Firehose  ──  GZIP, Hive-Prefix
  │
  ▼
S3  ──  events/year=.../month=.../day=.../
  │
  ▼
Athena + Glue  ──  SQL auf den Rohdaten
  │
  ▼
Lambda (stündlich)  ──  4 parallele Queries → S3-Cache
  │
  ▼
GET /dashboard  →  ECharts Frontend
```

Jeder Layer hat genau eine Aufgabe. Kein monolithischer Service, keine Datenbank die gewartet werden muss.

## Privacy by Design

Das war die erste und wichtigste Entscheidung. Die Regeln:

- **Keine IP-Adresse** wird gespeichert
- **Keine Cookies**, keine persistenten IDs
- **DNT wird respektiert** — wer Do Not Track gesetzt hat, wird nicht getrackt
- **Session-ID** ist ein daily-rotating SHA256-Hash: `SHA256(Datum + User-Agent + Screen-Breite)` — täglich neu, nicht rückverfolgbar, ermöglicht aber Unique-Visitor-Näherung

Das Tracking-Script im Blog ist bewusst minimal gehalten:

```javascript
if (navigator.doNotTrack === '1') return;

fetch('/track', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    page: location.pathname,
    lang: document.documentElement.lang,
    referrer: document.referrer ? new URL(document.referrer).hostname : '',
    screen_width: screen.width
  }),
  keepalive: true
}).catch(() => {});
```

`keepalive: true` stellt sicher dass der Request auch dann abgeschickt wird wenn der User direkt nach dem Seitenaufruf auf einen Link klickt. Das `.catch(() => {})` verhindert Konsolenfehler wenn Analytics mal nicht erreichbar ist.

## CloudFront Function: Cookies strippen

CloudFront leitet `/track`-Requests an API Gateway weiter. Damit keine Browser-Cookies an den Backend-Service gelangen, sitzt davor eine CloudFront Function:

```javascript
function handler(event) {
  var request = event.request;
  request.cookies = {};
  return request;
}
```

Drei Zeilen. Die Function läuft am Edge, bevor der Request das Origin überhaupt erreicht.

## Lambda: Bot-Filter und Session-Hash

Die Lambda-Funktion macht drei Dinge: Bots rausfiltern, Session-ID berechnen, Event in Firehose schreiben.

**Bot-Filterung** über den User-Agent:

```python
BOT_PATTERNS = re.compile(
    r'bot|crawl|spider|slurp|facebookexternalhit|'
    r'python-requests|curl|wget|go-http-client',
    re.IGNORECASE
)

if BOT_PATTERNS.search(ua):
    return {"statusCode": 200, "body": "ok"}
```

Bots bekommen ein stilles 200 — kein Fehler, kein Retry-Storm.

**Session-ID** ohne persistente Daten:

```python
date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
raw = f"{date_str}|{user_agent}|{screen_width}"
session_id = hashlib.sha256(raw.encode()).hexdigest()[:16]
```

Der Hash ändert sich täglich automatisch. Zwei Besuche desselben Users am gleichen Tag zählen als eine Session, am nächsten Tag als neue.

Das Event landet dann kompakt als JSON in Kinesis Firehose:

```python
record = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "event": "pageview",
    "page": body.get("page", ""),
    "lang": body.get("lang", ""),
    "referrer_domain": body.get("referrer", ""),
    "browser": browser,
    "screen_width": screen_width,
    "session_id": session_id,
}
firehose.put_record(
    DeliveryStreamName=STREAM_NAME,
    Record={"Data": (json.dumps(record) + "\n").encode()}
)
```

## Kinesis Firehose: Daten in S3

Firehose puffert Events (60 Sekunden oder 5 MB, je was zuerst kommt), komprimiert mit GZIP und schreibt in S3 mit Hive-kompatiblem Prefix:

```text
events/year=2026/month=05/day=18/analytics-1-2026-05-18-...gz
```

Dieses Format ermöglicht Athena, nur die relevanten Partitionen zu lesen — statt alle Daten zu scannen.

## Glue Table mit Partition Projection

Statt eines Glue Crawlers der regelmäßig laufen muss, nutze ich **Partition Projection**. Die Partitionsstruktur wird direkt im Glue-Schema deklariert:

```yaml
Parameters:
  projection.enabled: "true"
  projection.year.type: "integer"
  projection.year.range: "2026,2030"
  projection.month.type: "integer"
  projection.month.range: "1,12"
  projection.month.digits: "2"
  projection.day.type: "integer"
  projection.day.range: "1,31"
  projection.day.digits: "2"
  storage.location.template: "s3://BUCKET/events/year=${year}/month=${month}/day=${day}/"
```

Kein Crawler, keine täglichen Kosten für Metadaten-Updates. Athena berechnet die Partitionspfade selbst.

## Das Dashboard

Ein EventBridge-Schedule triggert stündlich eine Lambda, die vier Athena-Queries parallel ausführt:

```python
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {
        executor.submit(_run_query, name, sql): name
        for name, sql in _QUERIES.items()
    }
```

Die Queries:

| Query | Was |
| ------- | ----- |
| `daily_traffic` | Views + Unique Visitors pro Tag, letzte 30 Tage |
| `top_articles` | Top 10 Posts nach Views, letzte 30 Tage |
| `referrers` | Top 10 Traffic-Quellen, letzte 30 Tage |
| `devices` | Mobile / Tablet / Desktop nach Screen-Breite |

Das Ergebnis landet als `cache/dashboard.json` in S3. GET `/dashboard` liest diese Datei — Athena wird nicht bei jedem Dashboard-Aufruf abgefragt.

Das Frontend unter [/stats](/stats/) rendert die Daten mit ECharts, ist Dark-Mode-aware und lädt die Daten komplett clientseitig:

```javascript
fetch('/dashboard')
  .then(r => r.json())
  .then(d => render(d));
```

## Custom Domain: analytics.aws-sensei.cloud

Eine wichtige Architekturentscheidung: Die Analytics-API hat eine eigene Subdomain statt einer SSM-Parameter-Abhängigkeit zum Infra-Stack.

Das löst das Henne-Ei-Problem: CloudFront kann `analytics.aws-sensei.cloud` als Origin eingetragen haben, auch wenn die Analytics-API noch nicht existiert. Requests auf `/track` schlagen dann still fehl (`.catch(() => {})`), der Rest der Seite funktioniert normal. Sobald der Analytics-Stack deployed ist, funktioniert alles — ohne Infra-Stack neu deployen zu müssen.

## Kosten

Bei dem Traffic eines persönlichen Blogs: **unter einem Dollar pro Monat**.

- **Firehose**: $0.029 pro GB — bei wenigen KB Events täglich praktisch null
- **S3**: $0.023 pro GB Speicher + minimale PUT/GET-Kosten
- **Athena**: $5 pro TB gescannter Daten — mit GZIP + Partition Projection sind das wenige Cents pro Monat
- **Lambda**: kostenlos im Free Tier
- **EventBridge**: kostenlos für Standard-Schedules (erste Million Events/Monat)

Google Analytics ist kostenlos — aber der Preis ist Datenkontrolle und Datenschutz. Dieser Stack kostet Cent-Beträge und alle Daten gehören mir.

## Ergebnis

Das Dashboard ist live unter [/stats](/stats/). Tagesgang, Top-Artikel, Referrer und Geräte — alles aus eigenen Daten, ohne Drittanbieter, ohne Cookies.

**Update:** Der erste Betriebstag hat gezeigt, dass stündliche Athena-Queries über 30 Tage deutlich mehr S3-Requests erzeugen als erwartet. Wie ich das durch inkrementelles Caching von ~768.000 auf ~72 Requests pro Tag reduziert habe, beschreibe ich in [diesem Follow-up-Post](/posts/2026-05-28-analytics-cost-optimization/).

---

{{< chat >}}
