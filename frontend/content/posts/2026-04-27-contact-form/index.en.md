---
title: "Contact Form in the Blog — with AWS SES, Lambda and API Gateway"
date: 2026-04-27T00:00:00+02:00
lastmod: 2026-04-27T00:00:00+02:00
draft: false
author: "Marcel"
description: "How I built a serverless contact form into my blog — Lambda validates the input, SES sends the email."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Lambda", "API Gateway", "SES", "SAM", "Hugo", "Serverless"]
lightgallery: true
---

{{< listen >}}

Static blogs have no backend — but sometimes you still need a way for visitors to get in touch. The usual solution is a third-party service like Formspree or Netlify Forms. My solution: build everything on AWS myself.

## The Architecture

```text
Browser → API Gateway → Lambda → SES → Email
```

Three AWS services, all serverless. The visitor fills out the form, Lambda validates the input and calls SES — the email lands in my inbox.

## AWS SES

**Simple Email Service** is the AWS service for sending emails. It's cheap, reliable, and can be called directly from Lambda.

Before SES can send emails, the sender domain needs to be verified. Since `aws-sensei.cloud` is already in Route53, SES detects this automatically and adds the required DKIM records on its own — no manual DNS editing needed.

`noreply@aws-sensei.cloud` is used as the sender address. The visitor's email address goes into the `Reply-To` header — clicking "Reply" opens a direct response to the sender.

## The Lambda Handler

```python
ses.send_email(
    Source=FROM_EMAIL,
    Destination={"ToAddresses": [TO_EMAIL]},
    ReplyToAddresses=[email],
    Message={
        "Subject": {"Data": f"Blog contact from {name}"},
        "Body": {
            "Text": {
                "Data": f"Name: {name}\nE-Mail: {email}\n\n{message}"
            }
        },
    },
)
```

`TO_EMAIL` and `FROM_EMAIL` come from environment variables — no hardcoded addresses in the code.

Before calling SES, the Lambda validates the input: all three fields must be present, the email address is checked with a regex, and lengths are capped. Invalid requests are rejected with `400` without ever invoking SES.

## IAM

The Lambda gets exactly one permission:

```yaml
- Effect: Allow
  Action: ses:SendEmail
  Resource: "*"
```

No wildcard on actions — only what's actually needed.

## Throttling

The API Gateway has a rate limit: 1 request per second, burst up to 5. This protects against abuse without Lambda or SES ever being invoked.

## Hugo Shortcode

The form is embedded as a Hugo shortcode — HTML, CSS, and JavaScript in one file, no external framework. A `fetch()` to the API Gateway URL, evaluate the response, show the status.

## Try It Out

→ [Go to the contact page](/contact/)

---

{{< chat >}}
