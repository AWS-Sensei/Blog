---
title: "Intelligentere S3-Trigger: Hash-Dateien, SNS-Fanout und keine überflüssigen Lambda-Aufrufe mehr"
date: 2026-05-22T00:00:00+02:00
lastmod: 2026-05-22T00:00:00+02:00
draft: false
author: "Marcel"
description: "Wie eine 0-Byte-Datei mit MD5-Hash im Namen das KMS-ETag-Problem löst, überflüssige Lambda-Aufrufe eliminiert und die Tür für einen SNS-basierten Event-Fanout öffnet."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Lambda", "S3", "SNS", "Serverless", "CI/CD"]
lightgallery: true
---

{{< listen >}}

Das [Polly-TTS-Setup](/de/posts/2026-04-30-polly-tts/) funktionierte gut, hatte aber einen Makel: Jedes Deployment triggerte die Polly-Lambda für jeden Post — auch wenn sich nichts geändert hatte. Der Content-Hash-Check in der Lambda fing Duplikate nachträglich ab, aber die Aufrufe selbst passierten trotzdem für alle Posts bei jedem Push. Auf dem AWS Summit in Hamburg am 20. Mai hatte ich etwas Zeit, eine sauberere Lösung durchzudenken.

---

## Die Ursache

Der S3-Bucket verwendet SSE-KMS-Verschlüsselung. Wenn S3 ein Objekt mit KMS speichert, wird der ETag aus dem *verschlüsselten* Inhalt abgeleitet — nicht aus dem Klartext. `aws s3 sync` vergleicht den lokalen MD5 mit dem KMS-modifizierten ETag in S3, sie stimmen nie überein, und jede Markdown-Datei wird bei jedem Deployment neu hochgeladen — unabhängig davon ob der Inhalt sich geändert hat.

Jeder Upload feuert ein S3-Event. Jedes Event ruft die Lambda auf.

---

## Hash im Dateinamen

Die Lösung verschiebt die Deduplizierung in die Trigger-Datei selbst. Statt die Markdown-Dateien direkt zu syncen, berechnet die Pipeline einen MD5-Hash des Inhalts jedes Posts und erstellt eine 0-Byte-Datei die nach diesem Hash benannt ist:

```bash
hash=$(md5sum "$md_file" | cut -d' ' -f1)
touch "/tmp/post-triggers/$slug/index.$lang.$hash"
```

`aws s3 sync --size-only --delete` erledigt den Rest:

- **Gleicher Inhalt** → gleicher Hash → gleicher Dateiname → bereits in S3 → übersprungen, kein Event
- **Geänderter Inhalt** → neuer Hash → neuer Dateiname → hochgeladen → S3-Event → Lambda aufgerufen
- **`--delete`** entfernt die alte Hash-Datei wenn sich ein Post ändert — genau eine Trigger-Datei pro Post in S3

Das `--size-only`-Flag ist nötig weil alle Trigger-Dateien 0 Bytes groß sind — ohne es würde die KMS-ETag-Abweichung dazu führen dass jede Trigger-Datei bei jedem Deployment erneut hochgeladen wird.

Die Lambda selbst liest die Trigger-Datei nie. Sie extrahiert nur Slug und Sprache aus dem Key-Pfad um das gerenderte HTML in S3 zu finden.

---

## SNS-Fanout

Beim Überdenken des Triggers fiel ein zweites Problem auf: Die S3-Bucket-Notification zeigte direkt auf den Lambda-ARN der Polly-Funktion. Das erzeugte ein Henne-Ei-Problem beim Deployment — die Lambda musste existieren bevor der S3-Bucket vollständig konfiguriert werden konnte, was eine `HasPolly`-Condition im Infra-Stack erforderte.

Praktischer gedacht: Eine zweite Consumer-Lambda (zum Beispiel eine die neue Posts auf LinkedIn teilt) hätte jedes Mal eine Änderung an der S3-Notification-Config bedeutet.

Die Lösung: S3 publiziert stattdessen an ein SNS-Topic. Lambdas subscriben unabhängig.

```text
S3 (_content/posts/) → SNS sensei-post-changed → Polly Lambda
                                                → LinkedIn Lambda (demnächst)
```

Das SNS-Topic gehört zum Core-Infra-Stack. Consumer-Lambdas subscriben eigenständig — keine Stack-übergreifende Abhängigkeit, kein Henne-Ei-Problem.

---

## Idempotenz

SNS Standard liefert at-least-once. Wenn dasselbe Event zweimal ankommt, würde die Lambda Polly zweimal für denselben Inhalt aufrufen.

Der vorhandene Content-Hash-Check — ursprünglich für das KMS-Re-Upload-Problem geschrieben — dient gleichzeitig als Idempotenz-Guard:

```python
content_hash = hashlib.md5(text.encode()).hexdigest()

head = s3.head_object(Bucket=BUCKET, Key=audio_key)
if head.get("Metadata", {}).get("content-hash") == content_hash:
    print(f"Content unchanged, skipping: {audio_key}")
    return
```

Wenn dieselbe Nachricht zweimal geliefert wird, berechnet der zweite Aufruf denselben Hash, findet ihn bereits in den S3-Metadaten und beendet sich ohne Polly anzufassen. Der ursprüngliche Fix für das KMS-Problem übernimmt kostenlos die SNS-At-Least-Once-Garantie.

---

{{< chat >}}
