---
title: "LinkedIn OAuth Tokens Expire Every 60 Days — Here's the Serverless Re-Auth Fix"
date: 2026-07-01T00:00:00+02:00
lastmod: 2026-07-01T00:00:00+02:00
draft: false
author: "Marcel"
socialmedia: false
description: "LinkedIn access tokens expire after 60 days and there is no refresh token for standard apps. Here's how I built a one-click re-auth flow using AWS Lambda, API Gateway, and EventBridge."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Lambda", "LinkedIn API", "OAuth", "Secrets Manager", "SES", "SAM", "Serverless"]
lightgallery: true
---

{{< listen >}}

The automated LinkedIn pipeline I [built a few weeks ago](/posts/2026-05-26-automated-linkedin-posts-aws-bedrock/) worked well — until it would quietly stop working after 60 days. LinkedIn access tokens expire. And unlike most OAuth providers, LinkedIn does not issue refresh tokens to standard developer apps. When the token expires, posts stop.

This is the breakdown of the fix: a one-click re-authorization flow that takes about 30 seconds and runs entirely on AWS.

## Why There Is No Refresh Token

LinkedIn's OAuth 2.0 documentation mentions programmatic refresh tokens — but with a critical footnote:

> "LinkedIn supports programmatic refresh tokens for all approved **Marketing Developer Platform (MDP)** partners."

MDP is LinkedIn's enterprise partner program. A personal blog running the standard `w_member_social` scope is not an MDP app. The OAuth response simply never includes a `refresh_token` field. This is by design, not a configuration problem.

The only way to get a fresh access token is to run the full authorization code flow again — which requires a browser and a LinkedIn login. That can't be done fully programmatically, but it can be reduced to a single click.

## The Solution Architecture

```text
EventBridge (every Monday 8:00 UTC)
  → Lambda: ExpiryChecker
      ├─ Read expires_at from Secrets Manager
      ├─ If < 14 days remaining:
      └─ SES: send alert email with "Renew token" button

Email button: /linkedin/reauth
  → Lambda: ReauthFunction
      └─ 302 redirect → LinkedIn OAuth authorization URL

LinkedIn redirects to: /linkedin/callback?code=xxx
  → Lambda: CallbackFunction
      ├─ Exchange code for new access_token
      ├─ Calculate expires_at (now + expires_in seconds)
      └─ Secrets Manager: update access_token + expires_at
```

Three new Lambdas, one EventBridge rule, two new routes on the existing API Gateway — all added to the existing SAM template.

## The Re-Auth Lambda

When you click the button in the email, this Lambda fires. It reads `client_id` from Secrets Manager, builds the LinkedIn OAuth authorization URL, and returns a 302 redirect:

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

LinkedIn shows its standard authorization screen. You click "Allow" (or you're already logged in and it redirects immediately), and LinkedIn sends you to the callback URL with a short-lived `code` in the query string.

## The Callback Lambda

The callback exchanges the authorization code for a fresh access token and writes it back into Secrets Manager:

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

Existing fields (`person_id`, `client_id`, `client_secret`) are preserved — the secret is read, updated in memory, and written back. The success page shows the new expiry date.

## The Weekly Checker

An EventBridge rule fires every Monday at 8:00 UTC. The Lambda reads `expires_at` from Secrets Manager and sends an SES alert if the token expires within 14 days:

```python
def lambda_handler(event, context):
    secret = json.loads(secrets.get_secret_value(SecretId=LINKEDIN_SECRET_NAME)["SecretString"])
    expires_at_str = secret.get("expires_at")

    if not expires_at_str:
        send_alert("unknown", None)
        return

    days_left = (datetime.fromisoformat(expires_at_str) - datetime.now(timezone.utc)).days

    if days_left < 14:
        send_alert(...)
```

Missing `expires_at` also triggers an alert — useful for the first run after deployment, before any re-auth has happened.

## The Secret Structure

The existing `sensei/linkedin/oauth` secret gains two new fields:

```json
{
  "access_token": "...",
  "person_id": "...",
  "client_id": "...",
  "client_secret": "...",
  "expires_at": "2026-08-30T09:41:00+00:00"
}
```

`client_id` and `client_secret` were added manually once. `expires_at` is written automatically after each re-auth. The approver Lambda was already reading this secret — no changes needed there.

## The IAM Permissions

The callback Lambda needs one permission that the other Lambdas don't have: `secretsmanager:PutSecretValue`. Everything else reuses existing patterns.

```yaml
Policies:
  - Statement:
      - Effect: Allow
        Action:
          - secretsmanager:GetSecretValue
          - secretsmanager:PutSecretValue
        Resource: !Sub "arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:sensei/linkedin/oauth*"
```

`secretsmanager:*` was already in the CloudFormation execution role, so no infrastructure-level changes were needed.

## The End-to-End Flow

1. **Monday morning** — EventBridge triggers the checker
2. **Token < 14 days** — SES email arrives: "Token läuft in X Tagen ab"
3. **Click "Token erneuern"** — redirect to LinkedIn
4. **LinkedIn login / Allow** — redirect to `/linkedin/callback`
5. **Done** — success page shows new expiry date

Total time: about 30 seconds. The `expires_at` in Secrets Manager is updated, the pipeline continues working for another 60 days, and the whole cycle repeats.

---

{{< chat >}}
