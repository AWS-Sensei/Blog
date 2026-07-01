---
title: "LinkedIn OAuth-Token läuft alle 60 Tage ab — serverlose Lösung mit einem Klick"
date: 2026-07-01T00:00:00+02:00
lastmod: 2026-07-01T00:00:00+02:00
draft: false
author: "Marcel"
socialmedia: true
description: "LinkedIn-Access-Tokens laufen nach 60 Tagen ab — und für Standard-Apps gibt es keinen Refresh Token. Hier ist die Lösung: ein One-Click Re-Auth-Flow mit AWS Lambda, API Gateway und EventBridge."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Lambda", "LinkedIn API", "OAuth", "Secrets Manager", "SES", "SAM", "Serverless"]
lightgallery: true
---

{{< listen >}}

Die automatisierte LinkedIn-Pipeline, die ich [vor ein paar Wochen gebaut habe](/de/posts/2026-05-26-automated-linkedin-posts-aws-bedrock/), funktionierte gut — bis sie nach 60 Tagen stillschweigend aufgehört hätte zu funktionieren. LinkedIn-Access-Tokens laufen ab. Und anders als bei den meisten OAuth-Anbietern gibt es für Standard-Apps keinen Refresh Token. Wenn der Token abläuft, gehen keine Posts mehr raus.

Das hier ist die Aufschlüsselung der Lösung: ein One-Click Re-Auth-Flow, der etwa 30 Sekunden dauert und vollständig auf AWS läuft.

## Warum es keinen Refresh Token gibt

Die LinkedIn OAuth 2.0 Dokumentation erwähnt programmatische Refresh Tokens — aber mit einem entscheidenden Hinweis:

> "LinkedIn supports programmatic refresh tokens for all approved **Marketing Developer Platform (MDP)** partners."

MDP ist Linkedins Enterprise-Partnerprogramm. Ein persönlicher Blog mit dem Standard-Scope `w_member_social` ist keine MDP-App. Die OAuth-Antwort enthält schlicht kein `refresh_token`-Feld. Das ist kein Konfigurationsproblem, sondern absichtlich so.

Der einzige Weg zu einem frischen Access Token ist der vollständige Authorization Code Flow — der einen Browser und einen LinkedIn-Login erfordert. Das lässt sich nicht vollautomatisch lösen, aber auf einen einzigen Klick reduzieren.

## Die Lösungsarchitektur

```text
EventBridge (jeden Montag 8:00 UTC)
  → Lambda: ExpiryChecker
      ├─ expires_at aus Secrets Manager lesen
      ├─ Wenn < 14 Tage verbleibend:
      └─ SES: Alert-Mail mit "Token erneuern"-Button

Mail-Button: /linkedin/reauth
  → Lambda: ReauthFunction
      └─ 302 Redirect → LinkedIn OAuth Authorization URL

LinkedIn leitet weiter zu: /linkedin/callback?code=xxx
  → Lambda: CallbackFunction
      ├─ Code gegen neuen access_token tauschen
      ├─ expires_at berechnen (jetzt + expires_in Sekunden)
      └─ Secrets Manager: access_token + expires_at aktualisieren
```

Drei neue Lambdas, eine EventBridge Rule und zwei neue Routen am bestehenden API Gateway — alles ins vorhandene SAM-Template ergänzt.

## Die Re-Auth-Lambda

Beim Klick auf den Button in der Mail feuert diese Lambda. Sie liest die `client_id` aus Secrets Manager, baut die LinkedIn OAuth Authorization URL und gibt einen 302 Redirect zurück:

```python
def lambda_handler(event, context):
    secret = json.loads(secrets.get_secret_value(SecretId=LINKEDIN_SECRET_NAME)["SecretString"])

    params = urlencode({
        "response_type": "code",
        "client_id": secret["client_id"],
        "redirect_uri": REDIRECT_URI,
        "scope": "w_member_social",
    })

    return {
        "statusCode": 302,
        "headers": {"Location": f"https://www.linkedin.com/oauth/v2/authorization?{params}"},
        "body": "",
    }
```

LinkedIn zeigt seinen Standard-Autorisierungsscreen. Man klickt "Allow" — oder ist bereits eingeloggt und wird sofort weitergeleitet — und LinkedIn schickt einen mit einem kurzlebigen `code` im Query String zur Callback-URL.

## Die Callback-Lambda

Die Callback-Lambda tauscht den Authorization Code gegen einen frischen Access Token und schreibt ihn zurück in Secrets Manager:

```python
def lambda_handler(event, context):
    params = event.get("queryStringParameters") or {}
    code = params.get("code")

    secret = json.loads(secrets.get_secret_value(SecretId=LINKEDIN_SECRET_NAME)["SecretString"])

    body = urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": secret["client_id"],
        "client_secret": secret["client_secret"],
    }).encode("utf-8")

    with urlopen(Request("https://www.linkedin.com/oauth/v2/accessToken", data=body, ...)) as r:
        token_data = json.loads(r.read())

    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])).isoformat()

    secret["access_token"] = token_data["access_token"]
    secret["expires_at"] = expires_at
    secrets.put_secret_value(SecretId=LINKEDIN_SECRET_NAME, SecretString=json.dumps(secret))
```

Bestehende Felder (`person_id`, `client_id`, `client_secret`) bleiben erhalten — das Secret wird gelesen, im Speicher aktualisiert und zurückgeschrieben. Die Erfolgsseite zeigt das neue Ablaufdatum.

## Der wöchentliche Checker

Eine EventBridge Rule feuert jeden Montag um 8:00 UTC. Die Lambda liest `expires_at` aus Secrets Manager und schickt eine SES-Alert-Mail, wenn der Token in weniger als 14 Tagen abläuft:

```python
def lambda_handler(event, context):
    secret = json.loads(secrets.get_secret_value(SecretId=LINKEDIN_SECRET_NAME)["SecretString"])
    expires_at_str = secret.get("expires_at")

    if not expires_at_str:
        send_alert("unbekannt", None)
        return

    days_left = (datetime.fromisoformat(expires_at_str) - datetime.now(timezone.utc)).days

    if days_left < 14:
        send_alert(...)
```

Ein fehlendes `expires_at` löst ebenfalls einen Alert aus — nützlich beim ersten Lauf nach dem Deployment, bevor ein Re-Auth stattgefunden hat.

## Die Secret-Struktur

Das bestehende Secret `sensei/linkedin/oauth` bekommt zwei neue Felder:

```json
{
  "access_token": "...",
  "person_id": "...",
  "client_id": "...",
  "client_secret": "...",
  "expires_at": "2026-08-30T09:41:00+00:00"
}
```

`client_id` und `client_secret` wurden einmalig manuell hinzugefügt. `expires_at` wird automatisch nach jedem Re-Auth geschrieben. Die Approver-Lambda liest dieses Secret bereits — dort waren keine Änderungen nötig.

## Die IAM-Berechtigungen

Die Callback-Lambda braucht eine Permission, die die anderen Lambdas nicht haben: `secretsmanager:PutSecretValue`. Alles andere verwendet bestehende Patterns.

```yaml
Policies:
  - Statement:
      - Effect: Allow
        Action:
          - secretsmanager:GetSecretValue
          - secretsmanager:PutSecretValue
        Resource: !Sub "arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:sensei/linkedin/oauth*"
```

`secretsmanager:*` war bereits in der CloudFormation Execution Role — keine Änderungen auf Infrastrukturebene nötig.

## Der vollständige Flow

1. **Montag morgen** — EventBridge triggert den Checker
2. **Token < 14 Tage** — SES-Mail kommt: "Token läuft in X Tagen ab"
3. **Klick auf "Token erneuern"** — Redirect zu LinkedIn
4. **LinkedIn-Login / Allow** — Redirect zu `/linkedin/callback`
5. **Fertig** — Erfolgsseite zeigt das neue Ablaufdatum

Gesamtdauer: etwa 30 Sekunden. Das `expires_at` in Secrets Manager wird aktualisiert, die Pipeline läuft weitere 60 Tage, und der Zyklus wiederholt sich.

---

{{< chat >}}
