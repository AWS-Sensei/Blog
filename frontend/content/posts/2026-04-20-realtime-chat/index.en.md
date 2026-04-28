---
title: "Real-Time Comments in the Blog — with WebSocket API Gateway, Lambda and DynamoDB"
date: 2026-04-20T00:00:00+02:00
lastmod: 2026-04-20T00:00:00+02:00
draft: false
author: "Marcel"
description: "How I built a real-time chat as a comment section into my blog — WebSocket API Gateway, three Lambda functions and DynamoDB."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Lambda", "API Gateway", "DynamoDB", "WebSocket", "SAM", "Hugo", "Serverless"]
lightgallery: true
---

Static blogs have a problem: no interaction. Comment systems like Disqus exist, but they load third-party JavaScript, track visitors, and never quite fit the blog's look. My solution: build a custom real-time comment section directly on AWS.

The result is the widget at the bottom of this post — you can try it out right now.

## The Architecture

```text
Browser ←→ WebSocket API Gateway ←→ Lambda ←→ DynamoDB
```

The key difference from a regular REST widget: **WebSocket**. The connection stays open. When someone writes a message, every other visitor on the same post receives it immediately — no polling, no page reload.

## Why WebSocket Instead of REST?

With REST, the browser would have to keep asking: "Are there new messages?" — one HTTP request every second. That's wasteful and still not truly live.

With WebSocket, the browser opens one connection. The server can then push messages on its own — exactly when they arrive.

AWS provides this with **API Gateway WebSocket APIs**. AWS handles the connection management; I only write the Lambda functions for the individual events.

## The Data Structure

Two DynamoDB tables:

**`sensei-chat-connections`** — active WebSocket connections:

```text
connectionId (PK)   postSlug        ttl
wfK9dAx3=           2026-04-20-...  1714550400
```

TTL set to 24 hours — expired connections are deleted automatically.

**`sensei-chat-messages`** — persistent messages:

```text
postSlug (PK)          sortKey (SK)                    author    message
2026-04-20-realtime-  2026-04-20T...#a3f1c2d8          Marcel    First comment!
```

The sort key is `timestamp#uuid[:8]`. This enables chronological ordering via Query — without a Scan.

## The Three Lambda Functions

WebSocket API Gateway has three system routes: `$connect`, `$disconnect`, and `$default`. Each is handled by its own Lambda function.

### $connect — Opening a Connection

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

The browser connects with `?postSlug=2026-04-20-realtime-chat` — so the server knows which post this connection belongs to. API Gateway assigns the `connectionId` automatically.

### $disconnect — Closing a Connection

```python
def lambda_handler(event, context):
    connection_id = event["requestContext"]["connectionId"]
    connections.delete_item(Key={"connectionId": connection_id})
    return {"statusCode": 200}
```

When the browser closes or the connection drops, the entry is immediately removed from the table.

### $default — Processing Messages

The message Lambda handles two tasks — controlled via the `action` field in the JSON body:

**`getHistory`** — load message history:

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

**`sendMessage`** — save and broadcast a message:

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

`post_to_connection` sends a message to a specific connection. API Gateway handles the routing. If a connection no longer exists (browser closed, TTL not yet triggered), a `GoneException` is returned — the entry is then deleted from the table.

## Why Send getHistory Explicitly?

An earlier version loaded and pushed the history directly inside the `$connect` handler. That didn't work: the `$connect` handler runs before the WebSocket connection is fully established on the client side. The message was sent but never received.

The fix: the client sends a `getHistory` request itself after `onopen`. This guarantees the connection is ready.

```javascript
ws.onopen = function () {
  ws.send(JSON.stringify({ action: "getHistory", postSlug: POST_SLUG }));
};
```

## The SAM Template

`RouteSelectionExpression: "$request.body.action"` — this tells API Gateway to select the route based on the `action` field in the JSON body. `$connect` and `$disconnect` are system routes; all other messages land on `$default`.

```yaml
ChatWebSocketApi:
  Type: AWS::ApiGatewayV2::Api
  Properties:
    ProtocolType: WEBSOCKET
    RouteSelectionExpression: "$request.body.action"
```

For each route: one integration (Lambda ARN), one route resource, one Lambda permission.

## IAM

Three functions, three different permission sets:

| Function | DynamoDB | API Gateway |
| --- | --- | --- |
| connect | `PutItem` (connections) | — |
| disconnect | `DeleteItem` (connections) | — |
| message | `PutItem`, `Scan`, `DeleteItem` (connections) + `PutItem`, `Query` (messages) | `execute-api:ManageConnections` |

The message Lambda needs `ManageConnections` to call `post_to_connection`. Without this permission, every outbound WebSocket message fails.

## The Hugo Shortcode

```javascript
var ws = new WebSocket(WS_URL + "?postSlug=" + encodeURIComponent(POST_SLUG));

ws.onopen = function () {
  ws.send(JSON.stringify({ action: "getHistory", postSlug: POST_SLUG }));
};

ws.onclose = function () {
  setTimeout(connect, 3000);
};
```

`POST_SLUG` is set by Hugo at build time: `{{ .Page.File.Dir | path.Base }}`. This gives every blog post its own chat channel — with no manual configuration.

On connection loss, the client automatically reconnects after 3 seconds.

## Try It Out

---

{{< chat >}}
