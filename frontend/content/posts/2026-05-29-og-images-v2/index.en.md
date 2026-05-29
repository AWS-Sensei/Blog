---
title: "OG Image 2.0: From Hugo's Image Pipeline to Satori"
date: 2026-05-29T00:00:00+02:00
lastmod: 2026-05-29T00:00:00+02:00
draft: false
author: "Marcel"
socialmedia: false
description: "How I migrated OG image generation from Hugo's built-in image processing to a Satori-based Node.js pipeline — and why the result looks 10x better."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["Hugo", "Satori", "Node.js", "Open Graph", "CodeBuild", "sharp"]
lightgallery: true
---

{{< listen >}}

OG images are the preview cards that appear when you share a link on WhatsApp, LinkedIn, or Twitter. Nobody talks about them, but everyone sees them. A bad OG image is like a bad business card — technically it works, but it doesn't make a good impression.

My first OG images were bad.

## V1: Hugo's Built-In Image Pipeline

Hugo can process images. There's `images.Text`, `images.Overlay`, `images.Filter` — enough for simple use cases. My first approach: featured image on the left, text on the right, white background. Built entirely in Hugo templates, no external dependencies.

The result looked like a screenshot from 2012.

The real problem: Hugo's image pipeline is built for static processing, not dynamic layout. No Flexbox, no proper text wrapping, no bold font weight (Inter Bold TTF fails silently). And six different asset files for background, badge, button, photo frame, and mask — a maintenance nightmare.

## The Idea: Photo-First

I deliberately pick a matching featured image for every post. That effort should pay off. Instead of squeezing the image into 440px and placing it next to text: it *is* the OG image. Full-bleed, 1200×630px, with a dark gradient making the text readable.

The design is simple:

- Featured image fills the entire canvas
- Dark gradient from bottom: `rgba(0,0,0,0.88)` → `rgba(0,0,0,0.5)` → transparent
- Title and description in the bottom-left, white
- Domain badge top-right as a dark pill

No profile photo, no logo, no tags. The image speaks for itself.

## Why Satori?

[Satori](https://github.com/vercel/satori) is a library by Vercel that renders React JSX to SVG. With `@resvg/resvg-js` (Rust-based) the SVG is converted to PNG. This sounds like a detour, but it isn't — Satori supports real Flexbox layout, font weights, line breaks, and all the CSS properties you need for a proper design.

Alternatives would be `puppeteer` (Headless Chrome, ~300MB) or `canvas` (native Node.js bindings, complex setup). Satori is leaner and more deterministic — no browser, no OS rendering.

## The Stack

```json
{
  "satori": "^0.10.14",
  "@resvg/resvg-js": "^2.6.0",
  "sharp": "^0.34.5",
  "react": "^18.3.1",
  "gray-matter": "^4.0.3",
  "fast-glob": "^3.3.2"
}
```

The script runs as a Node.js build step before `hugo --minify`. Hugo itself no longer processes any images — it finds finished JPEGs in `static/og/` and links them directly.

## The Implementation

The full script is `frontend/scripts/generate-og.mjs`. It iterates over all `content/**/{index,_index}.*.md` files, reads frontmatter, and generates one JPEG per page.

**Preparing the background:**

```javascript
async function toDataUrl(filePath) {
  const resized = await sharp(filePath)
    .resize(1200, 630, { fit: 'cover', position: 'centre' })
    .jpeg({ quality: 90 })
    .toBuffer()
  return `data:image/jpeg;base64,${resized.toString('base64')}`
}
```

Satori receives images as data URLs. Featured images can be 6000×4000px JPEGs — embedded as base64 that would massively bloat the SVG string. `sharp` pre-scales the image to exactly 1200×630px, which is the only format Satori sees.

**The layout:**

```javascript
const el = h('div', { style: { width: 1200, height: 630, display: 'flex', position: 'relative' } },
  h('img', { src: bgDataUrl, style: { position: 'absolute', width: '100%', height: '100%', objectFit: 'cover' } }),
  h('div', { style: {
    position: 'absolute', bottom: 0, left: 0, right: 0, height: '75%',
    background: 'linear-gradient(to top, rgba(0,0,0,0.88) 0%, rgba(0,0,0,0.5) 55%, transparent 100%)'
  }}),
  h('div', { style: { position: 'absolute', top: 36, right: 46,
    backgroundColor: 'rgba(0,0,0,0.45)', borderRadius: 20, padding: '6px 16px',
    color: 'white', fontSize: 18 }
  }, 'aws-sensei.cloud'),
  h('div', { style: { position: 'absolute', bottom: 55, left: 60, right: 60,
    display: 'flex', flexDirection: 'column', gap: '14px' }},
    h('div', { style: { color: 'white', fontSize: 50, fontWeight: 700,
      WebkitLineClamp: 2, display: '-webkit-box', WebkitBoxOrient: 'vertical', overflow: 'hidden' }
    }, title),
    description && h('div', { style: { color: 'rgba(255,255,255,0.72)', fontSize: 22,
      WebkitLineClamp: 2, display: '-webkit-box', WebkitBoxOrient: 'vertical', overflow: 'hidden' }
    }, description),
  )
)
```

`h` is `createElement` from React — Satori expects React elements, not JSX. `WebkitLineClamp` ensures long titles are truncated after two lines.

**Output:**

```javascript
const svg = await satori(el, {
  width: 1200, height: 630,
  fonts: [{ name: 'Inter', data: fontData, weight: 700, style: 'normal' }],
})
const png = new Resvg(svg, { fitTo: { mode: 'width', value: 1200 } }).render().asPng()
return sharp(png).jpeg({ quality: 85 }).toBuffer()
```

`sharp` converts the PNG output from resvg to JPEG one more time. That's the key step for file size.

## Problems & Solutions

### 1. ESM/CJS conflict with fast-glob

```javascript
// This doesn't work:
import { glob } from 'fast-glob'  // SyntaxError: Named export 'glob' not found

// Fix:
import pkg from 'fast-glob'
const { glob } = pkg
```

fast-glob exports internally as CommonJS — in an ESM module you have to use the default import and destructure.

### 2. Input images too large

Featured images are often high-resolution photos (6000×4000px, several MB). Embedded as base64 in the SVG string, Satori would work with a massive data blob. The `toDataUrl` function therefore scales *before* embedding — Satori always gets only a 1200×630px JPEG.

### 3. PNG output ~1.2MB

Satori → resvg outputs PNG. PNG is lossless — for photos that makes no sense. `sharp(png).jpeg({ quality: 85 })` reduces a typical 1.2MB PNG to ~80-120KB JPEG. For social media thumbnails that's the right trade-off.

### 4. Homepage missing OG image

The homepage has no `content/posts/` file of its own — it's `content/_index.en.md` and `_index.de.md`. The script had to resolve the output path correctly: no directory name yields `index` as the slug:

```javascript
const slug = dir || 'index'
```

Hugo's `meta.html` has an analogous edge case for the German homepage (`/de` instead of `/de/index`).

### 5. Domain badge invisible on bright photos

White text on a white background isn't great design. The fix: a semi-transparent black pill as background — `rgba(0,0,0,0.45)` with `borderRadius: 20`. Looks good on dark and bright images alike.

## Build Integration

In `buildspec.yml` the script runs as the first build step:

```yaml
build:
  commands:
    - cd frontend
    - npm ci --omit=dev
    - node scripts/generate-og.mjs
    - hugo --minify
```

`static/og/` is gitignored — images are generated fresh on every build. Hugo finds them via `fileExists` and links them directly, without any image processing of its own.

```go
{{- $staticFile := printf "static/og%s.jpg" $relPath -}}
{{- if fileExists $staticFile -}}
  {{- $ogImage = printf "/og%s.jpg" $relPath | absURL -}}
{{- end -}}
```

`absURL` is critical: WhatsApp and other crawlers need an absolute URL — `https://aws-sensei.cloud/og/...` instead of `/og/...`.

## The Result

Hugo V1 worked — images were delivered and were small. The problem was the design: split layout, no bold, static, six asset files to maintain.

Satori without sharp: ~1.2MB PNG per image. Too large, but fixable. With sharp compression: ~100KB JPEG — smaller than the old Hugo images, better design.

If you put effort into choosing a fitting featured image for every post, that image should also show up in the OG preview. It's the simplest improvement with the biggest visual impact.

---

{{< chat >}}
