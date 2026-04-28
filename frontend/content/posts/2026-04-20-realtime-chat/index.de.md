---
title: "Echtzeit-Kommentare im Blog — mit WebSocket API Gateway, Lambda und DynamoDB"
date: 2026-04-20T00:00:00+02:00
lastmod: 2026-04-20T00:00:00+02:00
draft: false
author: "Marcel"
description: "Wie ich einen Echtzeit-Chat als Kommentarfunktion in meinen Blog eingebaut habe — WebSocket API Gateway, drei Lambda-Funktionen und DynamoDB."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Lambda", "API Gateway", "DynamoDB", "WebSocket", "SAM", "Hugo", "Serverless"]
lightgallery: true
---

Statische Blogs haben ein Problem: kein Austausch. Kommentarsysteme wie Disqus gibt es zwar, aber sie laden Drittanbieter-JavaScript, tracken Besucher und passen optisch nie wirklich zum Blog. Meine Lösung: eine eigene Echtzeit-Kommentarfunktion direkt auf AWS bauen.

Das Ergebnis ist das Widget am Ende dieses Posts — du kannst es gleich ausprobieren.

## Die Architektur

```text
Browser ←→ WebSocket API Gateway ←→ Lambda ←→ DynamoDB
```

Der entscheidende Unterschied zu einem normalen REST-Widget: **WebSocket**. Die Verbindung bleibt offen. Wenn jemand eine Nachricht schreibt, bekommen alle anderen Besucher des gleichen Posts sie sofort — ohne Polling, ohne Neuladen.

## Warum WebSocket statt REST?

Bei REST müsste der Browser regelmäßig fragen: "Gibt es neue Nachrichten?" — jede Sekunde ein HTTP-Request. Das ist verschwenderisch und trotzdem nicht wirklich live.

Mit WebSocket öffnet der Browser einmal eine Verbindung. Der Server kann dann selbst Nachrichten pushen — genau dann, wenn sie ankommen.

AWS bietet das mit **API Gateway WebSocket APIs** an. Die Verbindungsverwaltung übernimmt AWS, ich schreibe nur die Lambda-Funktionen für die einzelnen Events.

## Die Datenstruktur

Zwei DynamoDB-Tabellen:

**`sensei-chat-connections`** — aktive WebSocket-Verbindungen:

```text
connectionId (PK)   postSlug        ttl
wfK9dAx3=           2026-04-28-...  1714550400
```

TTL auf 24 Stunden gesetzt — abgelaufene Verbindungen werden automatisch gelöscht.

**`sensei-chat-messages`** — persistente Nachrichten:

```text
postSlug (PK)          sortKey (SK)                    author    message
2026-04-28-realtime-  2026-04-28T...#a3f1c2d8          Marcel    Erster Kommentar!
```

Der Sort Key ist `timestamp#uuid[:8]`. Das ermöglicht chronologische Sortierung per Query — ohne Scan.

## Die drei Lambda-Funktionen

WebSocket API Gateway kennt drei System-Routes: `$connect`, `$disconnect` und `$default`. Jede wird von einer eigenen Lambda-Funktion verarbeitet.

### $connect — Verbindung aufbauen

```python
def lambda_handler(event, context):
    connection_id = event["requestContext"]["connectionId"]
    post_slug = (event.get("queryStringParameters") or {}).get("postSlug", "global")

    connections.put_item(Item={
        "connectionId": connection_id,
        "postSlug": post_slug,
        "ttl": int(time.time()) + 86400,
    })

    return {"statusCode": 200}
```

Der Browser verbindet sich mit `?postSlug=2026-04-28-realtime-chat` — so weiß der Server, für welchen Post diese Verbindung zuständig ist. Die `connectionId` vergibt API Gateway automatisch.

### $disconnect — Verbindung beenden

```python
def lambda_handler(event, context):
    connection_id = event["requestContext"]["connectionId"]
    connections.delete_item(Key={"connectionId": connection_id})
    return {"statusCode": 200}
```

Wenn der Browser schließt oder die Verbindung abbricht, wird der Eintrag sofort aus der Tabelle entfernt.

### $default — Nachrichten verarbeiten

Die Message-Lambda übernimmt zwei Aufgaben — gesteuert über das `action`-Feld im JSON-Body:

**`getHistory`** — Nachrichtenverlauf laden:

```python
if action == "getHistory":
    result = messages.query(
        KeyConditionExpression=Key("postSlug").eq(post_slug),
        ScanIndexForward=True,
        Limit=50,
    )
    api_client.post_to_connection(
        ConnectionId=connection_id,
        Data=json.dumps({"type": "history", "messages": result["Items"]}).encode(),
    )
```

**`sendMessage`** — Nachricht speichern und broadcasten:

```python
messages.put_item(Item=message)

all_connections = connections.scan(
    FilterExpression=Attr("postSlug").eq(post_slug)
)

for conn in all_connections["Items"]:
    try:
        api_client.post_to_connection(ConnectionId=conn["connectionId"], Data=payload)
    except api_client.exceptions.GoneException:
        stale.append(conn["connectionId"])
```

`post_to_connection` schickt eine Nachricht an eine bestimmte Verbindung. API Gateway übernimmt das Routing. Wenn eine Verbindung nicht mehr existiert (Browser wurde geschlossen, TTL nicht ausgelöst), kommt eine `GoneException` zurück — dann wird der Eintrag aus der Tabelle gelöscht.

## Warum getHistory explizit senden?

Eine frühere Version hat den Verlauf direkt im `$connect`-Handler geladen und gepusht. Das hat nicht funktioniert: Der `$connect`-Handler läuft bevor die WebSocket-Verbindung auf Clientseite vollständig aufgebaut ist. Die Nachricht wurde versendet, aber nie empfangen.

Die Lösung: Der Client schickt nach `onopen` selbst eine `getHistory`-Anfrage. So ist die Verbindung garantiert bereit.

```javascript
ws.onopen = function () {
  ws.send(JSON.stringify({ action: "getHistory", postSlug: POST_SLUG }));
};
```

## Das SAM-Template

`RouteSelectionExpression: "$request.body.action"` — damit wählt API Gateway anhand des `action`-Felds im JSON-Body die Route aus. `$connect` und `$disconnect` sind Systemrouten, alle anderen Messages landen auf `$default`.

```yaml
ChatWebSocketApi:
  Type: AWS::ApiGatewayV2::Api
  Properties:
    ProtocolType: WEBSOCKET
    RouteSelectionExpression: "$request.body.action"
```

Für jede Route: eine Integration (Lambda-ARN), eine Route-Ressource, eine Lambda-Permission.

## IAM

Drei Funktionen, drei unterschiedliche Permission-Sets:

| Funktion | DynamoDB | API Gateway |
| --- | --- | --- |
| connect | `PutItem` (connections) | — |
| disconnect | `DeleteItem` (connections) | — |
| message | `PutItem`, `Scan`, `DeleteItem` (connections) + `PutItem`, `Query` (messages) | `execute-api:ManageConnections` |

Die Message-Lambda braucht `ManageConnections` um `post_to_connection` aufrufen zu können. Ohne diese Permission schlägt jede ausgehende WebSocket-Nachricht fehl.

## Der Hugo Shortcode

```javascript
var ws = new WebSocket(WS_URL + "?postSlug=" + encodeURIComponent(POST_SLUG));

ws.onopen = function () {
  ws.send(JSON.stringify({ action: "getHistory", postSlug: POST_SLUG }));
};

ws.onclose = function () {
  setTimeout(connect, 3000);
};
```

Der `POST_SLUG` wird von Hugo zur Build-Zeit gesetzt: `{{ .Page.File.Dir | path.Base }}`. Damit hat jeder Blog Post seinen eigenen Chat-Kanal — ohne manuelle Konfiguration.

Bei Verbindungsabbruch verbindet sich der Client nach 3 Sekunden automatisch neu.

## Ausprobieren

---

{{< chat >}}
