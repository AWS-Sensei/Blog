---
title: "Voiced by Amazon Polly — Text-to-Speech für einen statischen Blog"
date: 2026-04-30T00:00:00+02:00
lastmod: 2026-04-30T00:00:00+02:00
draft: false
author: "Marcel"
description: "Wie ich mit Amazon Polly, S3-Event-Triggern und einem Hugo-Shortcode automatisch Audio für jeden Blog-Post generiere — ohne den Static Site Generator anzufassen."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Polly", "Lambda", "Hugo", "Serverless"]
lightgallery: true
---

{{< listen >}}

Den Audio-Player oben hast du sicher schon bemerkt. Das ist Amazon Polly — der neuronale Text-to-Speech-Service von AWS. Hier ist wie es funktioniert und warum ich es so gebaut habe.

---

## Das Ziel

Jeder Blog-Post soll eine "Anhören"-Option haben. Audio wird automatisch generiert wenn ein Post veröffentlicht oder aktualisiert wird — keine manuellen Schritte, kein Drittanbieter.

---

## Architektur

```text
Git Push
  → Frontend Pipeline (Hugo Build + S3 Sync)
  → Markdown-Dateien nach S3 syncen (_content/posts/)
  → S3 Event triggert Lambda
  → Lambda liest HTML aus S3
  → Polly synthetisiert Sprache (SSML)
  → MP3 in S3 gespeichert (audio/{slug}.{lang}.mp3)
  → CloudFront liefert die Audio-Datei
```

---

## Warum Markdown als Trigger?

Der erste Gedanke war, auf die HTML-Dateien zu triggern die Hugo generiert. Das Problem: Hugo baut *alle* HTML-Dateien bei jedem Deployment neu — jeder Post würde bei jedem Push triggern.

Markdown-Dateien ändern sich nur wenn der Inhalt wirklich geändert wird. `aws s3 sync` vergleicht ETags und überspringt unveränderte Dateien — die Lambda feuert also nur für wirklich neue oder geänderte Posts.

---

## Warum HTML für den Text?

Die Lambda wird durch eine Markdown-Datei getriggert, liest aber das *HTML* aus S3 für den eigentlichen Inhalt.

Markdown-Dateien enthalten Hugo-Shortcodes (`{{</* chat */>}}`), Code-Blöcke und andere Syntax die mit komplexen Regex bereinigt werden müssten. Die HTML-Ausgabe ist bereits verarbeitet — Shortcodes sind gerendert oder verschwunden, Code-Blöcke stecken in `<pre>`-Tags die einfach zu erkennen und zu überspringen sind.

Die Lambda extrahiert nur den `<div id="content">`-Bereich, überspringt `<pre>`-Blöcke (ersetzt durch "Codebeispiel") und schließt Chat-Widget, Listen-Widget und Post-Footer aus.

---

## SSML für natürliche Pausen

Einfacher Text der an Polly gesendet wird klingt wie kontinuierliche Sprache ohne Atempausen zwischen Abschnitten. Mit SSML (Speech Synthesis Markup Language) füge ich nach jedem Absatz und jeder Überschrift eine 600ms-Pause ein:

```xml
<speak>
Erster Absatz.<break time="600ms"/>Zweiter Absatz.
</speak>
```

Das macht das Audio deutlich angenehmer zum Zuhören.

---

## Der Shortcode

Audio zu einem Post hinzufügen ist eine einzige Zeile:

```text
{{</* listen */>}}
```

Der Shortcode leitet die Audio-URL aus dem Verzeichnisnamen und der Sprache der Seite ab — keine Konfiguration nötig:

```text
/audio/2026-04-30-polly-tts.en.mp3
/audio/2026-04-30-polly-tts.de.mp3
```

Verwendete Stimmen: **Matthew** (Englisch) und **Daniel** (Deutsch) — beide Neural-Stimmen.

---

## Audio-Dateien schützen

Die Frontend-Pipeline verwendet `aws s3 sync --delete` um den S3-Bucket mit Hugos Ausgabe synchron zu halten. Ohne Ausnahmen würde das alle Audio-Dateien bei jedem Deployment löschen.

Die Lösung: `--exclude "audio/*" --exclude "_content/*"` — Audio-Dateien und der Markdown-Trigger-Prefix bleiben erhalten.

---

{{< chat >}}
