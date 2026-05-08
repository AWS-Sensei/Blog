---
title: "Voiced by Amazon Polly — Adding TTS to a Static Blog"
date: 2026-04-30T00:00:00+02:00
lastmod: 2026-04-30T00:00:00+02:00
draft: false
author: "Marcel"
description: "How I added Text-to-Speech to every blog post using Amazon Polly, S3 event triggers, and a Hugo shortcode — without touching the static site generator."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "Polly", "Lambda", "Hugo", "Serverless"]
lightgallery: true
---

{{< listen >}}

You've probably noticed the audio player at the top of this post. That's Amazon Polly — AWS's neural Text-to-Speech service. Here's how it works and why I built it the way I did.

---

## The Goal

Every blog post should have a "listen" option. Audio is generated automatically when a post is published or updated — no manual steps, no third-party service.

---

## Architecture

```text
Git Push
  → Frontend Pipeline (Hugo build + S3 sync)
  → Markdown files synced to S3 (_content/posts/)
  → S3 Event triggers Lambda
  → Lambda reads HTML from S3
  → Polly synthesizes speech (SSML)
  → MP3 saved to S3 (audio/{slug}.{lang}.mp3)
  → CloudFront serves the audio file
```

---

## Why Markdown as the Trigger?

The first instinct was to trigger on the HTML files that Hugo generates. The problem: Hugo rebuilds *all* HTML on every deployment, so every post would trigger on every push.

Markdown files only change when content actually changes. `aws s3 sync` compares ETags and skips unchanged files — so the Lambda only fires for genuinely new or updated posts.

---

## Why Read the HTML for Text?

The Lambda is triggered by a Markdown file upload but reads the *HTML* from S3 for the actual content.

Markdown files contain Hugo shortcodes (`{{</* chat */>}}`), code blocks, and other syntax that would need complex regex to clean up. The HTML output is already processed — shortcodes are rendered or gone, and code blocks are in `<pre>` tags that are easy to detect and skip.

The Lambda extracts only the `<div id="content">` area, skips `<pre>` blocks (replaced with "Code example"), and excludes the chat widget, listen widget, and post footer.

---

## SSML for Natural Pauses

Plain text sent to Polly results in continuous speech with no breathing room between sections. Using SSML (Speech Synthesis Markup Language), I insert a 600ms pause after every paragraph and heading:

```xml
<speak>
First paragraph.<break time="600ms"/>Second paragraph.
</speak>
```

This makes the audio significantly more pleasant to listen to.

---

## The Shortcode

Adding audio to a post is a single line:

```text
{{</* listen */>}}
```

The shortcode derives the audio URL from the page's directory name and language — no configuration needed:

```text
/audio/2026-04-30-polly-tts.en.mp3
/audio/2026-04-30-polly-tts.de.mp3
```

Voices used: **Matthew** (English) and **Daniel** (German) — both Neural voices.

---

## Keeping Audio Files Safe

The frontend pipeline uses `aws s3 sync --delete` to keep the S3 bucket in sync with Hugo's output. Without exclusions, this would delete all audio files on every deployment.

The fix: `--exclude "audio/*" --exclude "_content/*"` — audio files and the markdown trigger prefix are both preserved.

---

{{< chat >}}
