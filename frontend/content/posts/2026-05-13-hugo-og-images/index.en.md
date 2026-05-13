---
title: "Auto-Generated OG Images with Hugo"
date: 2026-05-13T00:00:00+02:00
lastmod: 2026-05-13T00:00:00+02:00
draft: false
author: "Marcel"
description: "How to generate social preview images at build time using Hugo's image processing pipeline — no Cloudinary, no Lambda, no external services."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["Hugo", "OG Images", "Static Site", "Social Sharing", "Build Pipeline"]
lightgallery: true
---

{{< listen >}}

When you share a blog post on LinkedIn or WhatsApp, the platform fetches the `og:image` meta tag and renders a preview. If the image is too large, too small, or missing entirely, you get nothing — just a plain link.

I ran into this with every post on this blog. WhatsApp showed no preview at all. The reason: the featured images were up to 6000×4000px and 2.8 MB. Way over WhatsApp's limit.

The fix I wanted: auto-generate a branded 1200×630px preview image at build time, directly inside Hugo — no Cloudinary, no Lambda function, no external service.

---

## What Hugo Can Do

Hugo has a built-in image processing pipeline that most people only use for resizing. But it also supports:

- `images.Overlay` — composite one image on top of another
- `images.Text` — render text onto an image with a custom font
- `images.Filter` — chain multiple operations together

That's enough to build a full OG image generator.

---

## The Layout

The design is a side-by-side layout: featured photo on the left, text on the right on a white background.

```text
┌────────────────────────────────────────────┐
│  ┌──────────┐   aws-sensei.cloud           │
│  │          │                              │
│  │  Photo   │   Post title here            │
│  │          │   wraps automatically        │
│  └──────────┘                              │
│               ┌──────────┐                 │
│               │ Read more│                 │
│               └──────────┘                 │
└────────────────────────────────────────────┘
```

The background is a PNG created with PowerShell's `System.Drawing` — a gradient from light gray on the left to white on the right.

---

## The Assets

Five static PNGs live in `assets/images/` and one font in `assets/fonts/`:

| File | Purpose |
| --- | --- |
| `og-bg.png` | 1200×630 gradient background |
| `og-badge.png` | Domain pill badge ("aws-sensei.cloud") |
| `og-btn.png` | "Read more" button |
| `og-btn-de.png` | "Weiterlesen" button for German posts |
| `og-photo-frame.png` | White rounded border behind the photo |
| `og-photo-mask.png` | Rounds the photo corners |
| `sans-regular.ttf` | Inter Regular for text rendering |

The badge and both buttons are created with PowerShell's `System.Drawing`, which lets you draw rounded rectangles, fill them, and render text — all without external tools:

```powershell
Add-Type -AssemblyName System.Drawing

$font = New-Object System.Drawing.Font("Segoe UI", 15, [System.Drawing.FontStyle]::Bold)
$bmp  = New-Object System.Drawing.Bitmap($w, $h, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g    = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

# Pill shape via GraphicsPath + AddArc
$path = New-Object System.Drawing.Drawing2D.GraphicsPath
$path.AddArc(0, 0, $r*2, $r*2, 180, 90)
# ... (remaining three corners)
$path.CloseFigure()

$g.FillPath([System.Drawing.Brushes]::Black, $path)
$g.DrawString("Read more", $font, [System.Drawing.Brushes]::White, $rect, $sf)

$bmp.Save("og-btn.png", [System.Drawing.Imaging.ImageFormat]::Png)
```

One important detail: the badge and buttons should be **the same width**. Measure the widest text first (`MeasureString`), add padding, and use that width for all elements.

---

## The Template

Hugo loads the OG template from `layouts/partials/head/meta.html`. The LoveIt theme has its own version — create a file at the same path in your project root to override it.

```go-html-template
{{- $bg      := resources.Get "images/og-bg.png" -}}
{{- $fontReg := resources.Get "fonts/sans-regular.ttf" -}}
{{- if and $bg $fontReg -}}
  {{- $canvas := $bg -}}

  {{- /* Photo with white rounded frame */ -}}
  {{- $frame := resources.Get "images/og-photo-frame.png" -}}
  {{- $mask  := resources.Get "images/og-photo-mask.png" -}}
  {{- with .Resources.GetMatch "featured-image*" -}}
    {{- $photo := .Fill "440x440 Center" -}}
    {{- if $frame -}}{{- $canvas = $canvas | images.Filter (images.Overlay $frame 35 90) -}}{{- end -}}
    {{- $canvas = $canvas | images.Filter (images.Overlay $photo 40 95) -}}
    {{- if $mask  -}}{{- $canvas = $canvas | images.Filter (images.Overlay $mask  40 95) -}}{{- end -}}
  {{- end -}}

  {{- /* Badge, title, language-aware button */ -}}
  {{- $badge := resources.Get "images/og-badge.png" -}}
  {{- $btn   := resources.Get "images/og-btn.png" -}}
  {{- if eq .Site.Language.Lang "de" -}}
    {{- $btn = resources.Get "images/og-btn-de.png" -}}
  {{- end -}}

  {{- if $badge -}}{{- $canvas = $canvas | images.Filter (images.Overlay $badge 560 150) -}}{{- end -}}
  {{- $canvas = $canvas | images.Filter
      (images.Text (printf "%s" $.Title)
        (dict "color" "#111827" "size" 36 "x" 560 "y" 230 "font" $fontReg)) -}}
  {{- if $btn -}}{{- $canvas = $canvas | images.Filter (images.Overlay $btn 560 390) -}}{{- end -}}

  {{- $ogImage = $canvas.Permalink -}}
{{- end -}}
```

---

## What Didn't Work (and Why)

**Bold fonts.** `images.Text` silently fails with Inter Bold TTF and OTF. Inter Regular works fine. I never found the root cause — switching to Regular was the fix.

**Variable mutation in `range` loops.** Hugo's Go templates don't persist variable assignments made inside `range` back to the outer scope in the way you'd expect. I spent a long time trying to build a word-wrap loop like this:

```go-html-template
{{- $l1 := "" -}}
{{- range split $.Title " " -}}
  {{- $l1 = printf "%s %s" $l1 . -}}  {{/* this doesn't stick outside the range */}}
{{- end -}}
```

The fix I tried (`.Scratch`) also didn't work reliably across all Hugo versions. In the end it turned out to be unnecessary: `images.Text` **automatically wraps text at the canvas boundary**. Pass the full title as a string — Hugo handles the line breaks.

**`template.HTML` vs `string`.** Hugo's `truncate` and some string functions return `template.HTML`, not `string`. Passing that directly to `images.Text` causes a silent failure. Wrap with `printf "%s"` to convert:

```go-html-template
{{- $canvas = $canvas | images.Filter
    (images.Text (printf "%s" $.Title) ...) -}}
```

**Rounded photo corners.** The white border frame (`og-photo-frame.png`) and the corner mask (`og-photo-mask.png`) need geometrically consistent radii. With a 5px border and a frame corner radius `R`, the photo's corners are at position `(5, 5)` relative to the frame corner. That point must fall *inside* the frame's rounded area. The condition:

```text
sqrt((R-5)² + (R-5)²) ≤ R  →  R ≤ 17px
```

Use `radius=12` for the frame and `radius=8` for the mask to stay safe.

---

## Keeping the Cache Out of Git

Hugo stores processed image derivatives in `resources/_gen/images/`. These files are content-addressed — change the title text and every hash changes. Committing them creates noisy diffs.

Add this to `.gitignore`:

```text
/frontend/resources/_gen/images/
```

Hugo regenerates the cache on every build. For a blog with ~15 posts, that adds a few seconds to the pipeline — a fair trade.

---

## Result

Every post now gets a 1200×630px OG image generated at build time:

- Correct size for WhatsApp, LinkedIn, Twitter/X
- Branded with the domain badge
- Title auto-wrapped to fit the layout
- German posts get "Weiterlesen", English posts get "Read more"
- Zero runtime cost — it's just static files on S3

The only thing Hugo can't do: rotate the photo at an arbitrary angle (only 90° increments are supported). For that you'd need a build-time script with Pillow or `@napi-rs/canvas`. A future post, maybe.

---

{{< chat >}}
