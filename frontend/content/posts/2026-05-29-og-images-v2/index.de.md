---
title: "OG Image 2.0: Von Hugo's Image Pipeline zu Satori"
date: 2026-05-29T00:00:00+02:00
lastmod: 2026-05-29T00:00:00+02:00
draft: false
author: "Marcel"
socialmedia: true
description: "Wie ich OG-Image-Generierung von Hugo's eingebautem Image-Processing zu einer Satori-basierten Node.js-Pipeline migriert habe — und warum das Ergebnis 10x besser aussieht."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["Hugo", "Satori", "Node.js", "Open Graph", "CodeBuild", "sharp"]
lightgallery: true
---

{{< listen >}}

OG Images sind diese Vorschau-Bilder, die erscheinen wenn man einen Link in WhatsApp, LinkedIn oder Twitter teilt. Niemand redet drüber, aber jeder sieht sie. Ein schlechtes OG Image ist wie eine schlechte Visitenkarte — technisch erfüllt es seinen Zweck, aber es macht keinen guten Eindruck.

Meine ersten OG Images waren schlecht.

## V1: Hugo's eingebaute Image Pipeline

Hugo kann Bilder verarbeiten. Es gibt `images.Text`, `images.Overlay`, `images.Filter` — ausreichend für einfache Use Cases. Mein erster Ansatz: das Featured Image links, Text rechts, weißer Hintergrund. Komplett in Hugo-Templates gebaut, keine externe Abhängigkeit.

Das Ergebnis sah aus wie ein Screenshot aus 2012.

Das eigentliche Problem: Hugo's Image Pipeline ist für statische Verarbeitung gebaut, nicht für dynamisches Layout. Kein Flexbox, kein richtiges Text-Wrapping, kein Bold-Weight (Inter Bold TTF scheitert lautlos). Und sechs verschiedene Asset-Dateien für Hintergrund, Badge, Button, Foto-Rahmen und Maske — ein Wartungsalptraum.

## Die Idee: Photo-First

Ich suche für jeden Post bewusst ein passendes Featured Image. Das sollte sich lohnen. Statt das Bild auf 440px zu quetschen und neben Text zu stellen: es *ist* das OG Image. Vollflächig, 1200×630px, mit einem dunklen Gradienten der den Text lesbar macht.

Das Design ist simpel:

- Featured Image füllt die gesamte Fläche
- Dunkler Gradient von unten: `rgba(0,0,0,0.88)` → `rgba(0,0,0,0.5)` → transparent
- Titel und Beschreibung unten links, weiß
- Domain-Badge oben rechts als dunkle Pill

Kein Profilbild, kein Logo, keine Tags. Das Bild spricht für sich.

## Warum Satori?

[Satori](https://github.com/vercel/satori) ist eine Bibliothek von Vercel, die React JSX zu SVG rendert. Mit `@resvg/resvg-js` (Rust-basiert) wird das SVG dann zu PNG. Das klingt nach Umweg, ist es aber nicht — Satori unterstützt echtes Flexbox-Layout, Schriftgewichte, Zeilenumbrüche und alle CSS-Properties die man für ein anständiges Design braucht.

Alternativen wären `puppeteer` (Headless Chrome, ~300MB) oder `canvas` (native Node.js Bindings, komplexes Setup). Satori ist schlanker und deterministischer — kein Browser, kein OS-Rendering.

## Der Stack

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

Das Script läuft als Node.js Build-Step vor `hugo --minify`. Hugo selbst verarbeitet keine Bilder mehr — es findet fertige JPEGs in `static/og/` und verlinkt sie direkt.

## Die Implementierung

Das komplette Script ist `frontend/scripts/generate-og.mjs`. Es durchläuft alle `content/**/{index,_index}.*.md` Dateien, liest Frontmatter, und generiert pro Seite ein JPEG.

**Hintergrund aufbereiten:**

```javascript
async function toDataUrl(filePath) {
  const resized = await sharp(filePath)
    .resize(1200, 630, { fit: 'cover', position: 'centre' })
    .jpeg({ quality: 90 })
    .toBuffer()
  return `data:image/jpeg;base64,${resized.toString('base64')}`
}
```

Satori bekommt Bilder als Data-URL. Featured Images können 6000×4000px große JPEGs sein — als base64 eingebettet würde das den SVG-String massiv aufblähen. `sharp` skaliert das Bild vorher auf exakt 1200×630px runter, das ist das einzige Format das Satori sieht.

**Das Layout:**

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

`h` ist `createElement` aus React — Satori erwartet React-Elemente, kein JSX. `WebkitLineClamp` sorgt dafür, dass lange Titel nach zwei Zeilen abgeschnitten werden.

**Output:**

```javascript
const svg = await satori(el, {
  width: 1200, height: 630,
  fonts: [{ name: 'Inter', data: fontData, weight: 700, style: 'normal' }],
})
const png = new Resvg(svg, { fitTo: { mode: 'width', value: 1200 } }).render().asPng()
return sharp(png).jpeg({ quality: 85 }).toBuffer()
```

`sharp` wandelt den PNG-Output von resvg noch einmal zu JPEG um. Das ist der entscheidende Schritt für die Dateigröße.

## Probleme & Lösungen

### 1. ESM/CJS Konflikt mit fast-glob

```javascript
// Das funktioniert nicht:
import { glob } from 'fast-glob'  // SyntaxError: Named export 'glob' not found

// Fix:
import pkg from 'fast-glob'
const { glob } = pkg
```

fast-glob exportiert intern als CommonJS — in einem ESM-Modul muss man den Default-Import verwenden und destructuren.

### 2. Input-Bilder zu groß

Featured Images sind oft hochauflösende Fotos (6000×4000px, mehrere MB). Als base64 in den SVG-String eingebettet würde Satori mit einem riesigen Daten-Blob arbeiten. Die `toDataUrl`-Funktion skaliert daher *vor* dem Einbetten — Satori bekommt immer nur ein 1200×630px JPEG.

### 3. PNG-Output ~1,2MB

Satori → resvg gibt PNG aus. PNG ist verlustfrei — für Fotos macht das keinen Sinn. `sharp(png).jpeg({ quality: 85 })` reduziert eine typische 1,2MB PNG auf ~80-120KB JPEG. Für Social-Media-Thumbnails ist das der richtige Trade-off.

### 4. Homepage ohne OG Image

Die Homepage hat keine eigene `content/posts/`-Datei — sie ist `content/_index.en.md` und `_index.de.md`. Das Script musste dafür den Ausgabepfad richtig auflösen: kein Verzeichnisname ergibt `index` als Slug:

```javascript
const slug = dir || 'index'
```

Hugo's `meta.html` hat einen analogen Sonderfall für die DE-Homepage (`/de` statt `/de/index`).

### 5. Domain-Badge auf hellen Fotos nicht sichtbar

Weißer Text auf weißem Hintergrund ist kein gutes Design. Die Lösung: ein halbtransparentes schwarzes Pill als Hintergrund — `rgba(0,0,0,0.45)` mit `borderRadius: 20`. Sieht auf dunklen wie auf hellen Bildern gut aus.

## Integration in den Build

In `buildspec.yml` läuft das Script als erster Build-Schritt:

```yaml
build:
  commands:
    - cd frontend
    - npm ci --omit=dev
    - node scripts/generate-og.mjs
    - hugo --minify
```

`static/og/` ist gitignored — die Bilder werden bei jedem Build frisch generiert. Hugo findet sie per `fileExists` und verlinkt sie direkt, ohne eigenes Image-Processing.

```go
{{- $staticFile := printf "static/og%s.jpg" $relPath -}}
{{- if fileExists $staticFile -}}
  {{- $ogImage = printf "/og%s.jpg" $relPath | absURL -}}
{{- end -}}
```

`absURL` ist entscheidend: WhatsApp und andere Crawler brauchen eine absolute URL — `https://aws-sensei.cloud/og/...` statt `/og/...`.

## Das Ergebnis

Hugo V1 hat funktioniert — die Images wurden ausgeliefert und waren klein. Das Problem war das Design: Split-Layout, kein Bold, statisch, sechs Asset-Dateien zum Pflegen.

Satori ohne sharp: ~1,2MB PNG pro Image. Zu groß, aber lösbar. Mit sharp-Komprimierung: ~100KB JPEG — kleiner als die alten Hugo-Images, besseres Design.

Wer auf jedem Post ein sorgfältig ausgewähltes Featured Image hat, sollte es auch im OG Image zeigen. Das ist die einfachste Verbesserung mit dem größten visuellen Impact.

---

{{< chat >}}
