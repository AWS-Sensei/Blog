---
title: "Automatische LinkedIn-Posts mit AWS Lambda und Bedrock — Approval-First Workflow"
date: 2026-05-26T00:00:00+02:00
lastmod: 2026-05-26T00:00:00+02:00
draft: false
author: "Marcel"
socialmedia: false
description: "Wie ich eine serverlose Pipeline gebaut habe, die automatisch LinkedIn-Posts aus neuen Blog-Artikeln generiert — mit AWS Lambda, Bedrock und einem Approval-Workflow."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Lambda", "Bedrock", "SNS", "DynamoDB", "SES", "LinkedIn API", "SAM", "Serverless"]
lightgallery: true
---

{{< listen >}}

Blog-Posts zu schreiben ist eine Sache. Dafür zu sorgen, dass sie auch gelesen werden, eine andere. LinkedIn wäre ein naheliegender Kanal — aber wenn man schon automatisiert, dann richtig. Also habe ich direkt eine Pipeline gebaut, die neue Artikel automatisch als LinkedIn-Post aufbereitet — mit einem Approval-Schritt dazwischen, denn KI-generierter Text der ohne Review direkt veröffentlicht wird, ist keine Option.

## Die Idee

Jeder neue englische Blog-Post soll automatisch einen LinkedIn-Post-Entwurf triggern, generiert von Claude über Amazon Bedrock. Ich reviewe ihn, klicke auf Approve — und er geht live. Kein Scheduler, kein Cron-Job. Der Klick auf Approve *ist* der Publish-Trigger.

Die Architektur sieht so aus:

```text
S3: neuer Artikel deployed
  → SNS: sensei-post-changed
    → Lambda: Orchestrator
        ├─ Sprachcheck (.en. im Key)
        ├─ Frontmatter-Check (socialmedia: true)
        ├─ Bedrock: LinkedIn-Post generieren
        ├─ DynamoDB: speichern (status: pending)
        └─ SES: Approval-Mail versenden

E-Mail-Link: /approve?postId=xxx
  → Lambda: Approver
      ├─ DynamoDB: pending → publishing  (Distributed Lock)
      ├─ LinkedIn Share API: posten
      └─ DynamoDB: publishing → sent + postUrl
```

## Der Trigger-Mechanismus

Die Frontend-Pipeline hatte bereits etwas Nützliches: Nach jedem Hugo-Build werden Hash-basierte Trigger-Dateien nach S3 synchronisiert:

```bash
find content/posts -name "*.md" | while read md_file; do
  slug=$(echo "$md_file" | cut -d'/' -f3)
  lang=$(basename "$md_file" | cut -d'.' -f2)
  hash=$(md5sum "$md_file" | cut -d' ' -f1)
  mkdir -p "/tmp/post-triggers/$slug"
  cp "$md_file" "/tmp/post-triggers/$slug/index.$lang.$hash"
done
aws s3 sync /tmp/post-triggers/ s3://$WEBSITE_BUCKET/_content/posts/ --size-only --delete
```

Ändert sich ein Post, ändert sich der Hash, eine neue Datei wird hochgeladen, S3 feuert ein `PutObject`-Event an ein SNS-Topic. Das Topic war bereits vorhanden — ich musste nur eine Lambda darauf subscriben.

Eine wichtige Änderung: Vorher waren das leere `touch`-Dateien mit dem Hash im Dateinamen. Ich habe sie auf `cp` umgestellt — die Datei *ist* jetzt das Markdown. Die Lambda liest den Objektinhalt direkt aus dem S3-Event, kein zweiter Lookup nötig.

## Das Frontmatter-Flag

Nicht jeder Post soll automatisch einen LinkedIn-Post generieren. Ich habe ein einfaches Boolean ins Hugo-Frontmatter ergänzt:

```yaml
---
title: "Mein Post"
socialmedia: true
---
```

Die Lambda prüft das als erstes nach dem Sprachfilter. Kein `socialmedia: true` → silent return, nichts passiert.

## SNS-Filterrichtlinien und eine Überraschung

Ich wollte Englisch-Posts direkt in der SNS-Subscription filtern, mit dem `contains`-Operator auf dem S3-Objekt-Key:

```json
{"Records": {"s3": {"object": {"key": [{"contains": ".en."}]}}}}
```

Das funktioniert über die AWS API. In CloudFormation-Templates funktioniert es **nicht**. Der `contains`-String-Operator für SNS-Filterrichtlinien wird in CloudFormation nicht unterstützt — es gibt einen Validierungsfehler beim Deploy. Vorerst: Filter in die Lambda verschieben.

```python
if ".en." not in key:
    print(f"Überspringe {key}: kein englischer Post")
    return
```

Eine Zeile. Funktioniert genauso gut.

## Die LinkedIn Developer App einrichten

Der LinkedIn-API-Zugang war der reibungsintensivste Teil. Das Developer-Portal verlangt, dass jede App einer Company Page zugeordnet wird. Für Individual Developers stellt LinkedIn eine **"Default Company Page for Individual Users"** bereit — das ist allerdings nirgends klar dokumentiert. Die Seite ist im Formular bereits vorausgewählt, aber so beschriftet, dass es aussieht, als müsste man erst selbst etwas erstellen.

Muss man nicht. Einfach auswählen und weitermachen.

{{< expand "Screenshot: Default Company Page für Individual Users" >}}
{{< figure src="linkedin-default-company-page.png" >}}
{{< /expand >}}

Die benötigten OAuth Scopes:

- `w_member_social` — zum Posten (via Produkt "Share on LinkedIn")
- `openid` + `profile` — zum Lesen der Person-ID (via Produkt "Sign In with LinkedIn using OpenID Connect")

Beide Produkte werden für Individual Developers sofort genehmigt.

Nach dem OAuth-Flow speichert man `access_token` und `person_id` im Secrets Manager:

```bash
aws secretsmanager put-secret-value \
  --secret-id sensei/linkedin/oauth \
  --secret-string '{"access_token":"...","person_id":"..."}'
```

Hinweis: LinkedIn Access Tokens laufen nach 60 Tagen ab. Token-Refresh steht auf dem Backlog.

## Idempotenz

Zwei Fehlermodi sind zu bedenken:

**SNS At-least-once Delivery** — die Orchestrator-Lambda könnte für dasselbe S3-Event mehrfach aufgerufen werden. Eine zufällige UUID als `postId` würde doppelte Pending-Posts erzeugen. Fix: deterministische ID aus dem S3-Key:

```python
post_id = hashlib.md5(key.encode()).hexdigest()

table.put_item(
    Item={...},
    ConditionExpression="attribute_not_exists(postId)",
)
```

Der zweite Aufruf scheitert an der Bedingung und kehrt still zurück.

**Gleichzeitige Approval-Klicks** — zwei schnelle Klicks auf den E-Mail-Link könnten die LinkedIn API zweimal aufrufen, bevor DynamoDB aktualisiert ist. Der naive Fix (Conditional Update nach dem Posten) hilft nicht, weil beide Aufrufe den Status-Check bereits bestanden haben.

Der richtige Fix: Post *vor* dem LinkedIn-Aufruf mit einem `publishing`-Zwischenstatus beanspruchen:

```python
# Schritt 1: atomarer Claim — nur eine Lambda gewinnt
table.update_item(
    ConditionExpression="#s = :pending",
    UpdateExpression="SET #s = :publishing",
    ...
)

# Schritt 2: jetzt sicher LinkedIn aufrufen
post_url = post_to_linkedin(access_token, person_id, content)

# Schritt 3: als gesendet markieren
table.update_item(UpdateExpression="SET #s = :sent, postUrl = :url", ...)
```

Das `pending → publishing` Update ist in DynamoDB atomar. Das Conditional Update der zweiten Lambda schlägt sofort fehl — bevor ein LinkedIn-API-Aufruf stattfindet.

## Warum Approval-First?

Der Approval-Schritt ist kein Overhead — er ist das Feature. KI-generierter Text klingt manchmal schief, trifft den falschen Ton oder betont das Falsche. Ein menschlicher Review-Schritt bevor etwas veröffentlicht wird, hält die Qualität dort, wo sie sein soll.

Der Workflow:

1. Blog-Post mit `socialmedia: true` veröffentlichen
2. E-Mail-Vorschau mit dem generierten LinkedIn-Post erhalten
3. Auf "Approve & Post to LinkedIn" klicken
4. Fertig

Der Klick IST das Veröffentlichen. Kein Scheduler nötig, kein Optimal-Zeit-Algorithmus. Der richtige Zeitpunkt zum Posten ist der, zu dem man es entscheidet.

## Was als Nächstes kommt

- Token-Refresh vor dem 60-Tage-Ablauf
- Bearbeitungsfunktion in der Approval-Mail (falls der generierte Post angepasst werden muss)

---

{{< chat >}}
