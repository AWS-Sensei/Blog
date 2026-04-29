---
title: "Kontaktformular im Blog — mit AWS SES, Lambda und API Gateway"
date: 2026-04-27T00:00:00+02:00
lastmod: 2026-04-27T00:00:00+02:00
draft: false
author: "Marcel"
description: "Wie ich ein serverless Kontaktformular in meinen Blog eingebaut habe — Lambda validiert die Eingabe, SES verschickt die E-Mail."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Lambda", "API Gateway", "SES", "SAM", "Hugo", "Serverless"]
lightgallery: true
---

Statische Blogs haben kein Backend — aber manchmal braucht man trotzdem einen Weg damit Besucher Kontakt aufnehmen können. Die übliche Lösung ist ein Drittanbieter-Dienst wie Formspree oder Netlify Forms. Meine Lösung: alles selbst auf AWS bauen.

## Die Architektur

```text
Browser → API Gateway → Lambda → SES → E-Mail
```

Drei AWS Services, alle serverless. Der Besucher füllt das Formular aus, Lambda validiert die Eingabe und ruft SES auf — die E-Mail landet bei mir.

## AWS SES

**Simple Email Service** ist der AWS-Dienst zum Versenden von E-Mails. Er ist günstig, zuverlässig und lässt sich direkt aus Lambda aufrufen.

Bevor SES E-Mails versenden darf, muss die Absender-Domain verifiziert werden. Da `aws-sensei.cloud` bereits in Route53 liegt, erkennt SES das automatisch und trägt die nötigen DKIM-Records selbst ein — kein manuelles DNS-Editieren nötig.

Als Absender wird `noreply@aws-sensei.cloud` verwendet. Die E-Mail-Adresse des Besuchers landet im `Reply-To`-Header — ein Klick auf "Antworten" öffnet also direkt die Antwort an den Absender.

## Der Lambda-Handler

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

`TO_EMAIL` und `FROM_EMAIL` kommen aus Environment Variables — keine hardcodierten Adressen im Code.

Vor dem SES-Aufruf validiert die Lambda die Eingabe: alle drei Felder müssen vorhanden sein, die E-Mail-Adresse wird per Regex geprüft, Längen sind begrenzt. Ungültige Requests werden mit `400` abgewiesen, ohne dass SES aufgerufen wird.

## IAM

Die Lambda bekommt genau eine Permission:

```yaml
- Effect: Allow
  Action: ses:SendEmail
  Resource: "*"
```

Kein Wildcard auf Actions — nur was tatsächlich gebraucht wird.

## Throttling

Das API Gateway hat ein Rate-Limit: 1 Request pro Sekunde, Burst bis 5. Das schützt vor Missbrauch ohne dass Lambda oder SES überhaupt aufgerufen werden.

## Hugo Shortcode

Das Formular ist als Hugo Shortcode eingebunden — HTML, CSS und JavaScript in einer Datei, kein externes Framework. Ein `fetch()` auf die API Gateway URL, Antwort auswerten, Status anzeigen.

## Ausprobieren

→ [Zur Kontaktseite](/de/contact/)

---

{{< chat >}}
