---
title: "Automatische OG-Images mit Hugo"
date: 2026-05-13T00:00:00+02:00
lastmod: 2026-05-13T00:00:00+02:00
draft: false
author: "Marcel"
description: "Wie man Social-Preview-Bilder zur Build-Zeit direkt in Hugo generiert — ohne Cloudinary, ohne Lambda, ohne externe Dienste."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["Hugo", "OG Images", "Static Site", "Social Sharing", "Build Pipeline"]
lightgallery: true
---

{{< listen >}}

Wenn man einen Blog-Post auf LinkedIn oder WhatsApp teilt, liest die Plattform den `og:image`-Meta-Tag aus und zeigt eine Vorschau an. Ist das Bild zu groß, zu klein oder fehlt es ganz, sieht man nur einen nackten Link.

Genau das passierte bei jedem Post auf diesem Blog. WhatsApp zeigte gar nichts an. Der Grund: die Featured-Images waren bis zu 6000×4000px groß und 2,8 MB schwer — weit über WhatsApps Limit.

Was ich wollte: zur Build-Zeit automatisch ein gebrandetes 1200×630px-Vorschaubild generieren, direkt in Hugo — kein Cloudinary, keine Lambda-Funktion, kein externer Dienst.

---

## Was Hugo kann

Hugo hat eine eingebaute Bildverarbeitungs-Pipeline, die die meisten nur zum Skalieren nutzen. Sie unterstützt aber auch:

- `images.Overlay` — ein Bild auf ein anderes legen
- `images.Text` — Text mit einer eigenen Schriftart in ein Bild rendern
- `images.Filter` — mehrere Operationen verketten

Das reicht für einen vollständigen OG-Image-Generator.

---

## Das Layout

Das Design ist ein Side-by-Side-Layout: Featured-Photo links, Text rechts auf weißem Hintergrund.

```text
┌────────────────────────────────────────────┐
│  ┌──────────┐   aws-sensei.cloud           │
│  │          │                              │
│  │   Foto   │   Post-Titel hier            │
│  │          │   bricht automatisch um      │
│  └──────────┘                              │
│               ┌────────────┐               │
│               │ Weiterlesen│               │
│               └────────────┘               │
└────────────────────────────────────────────┘
```

Der Hintergrund ist eine PNG-Datei, die mit PowerShells `System.Drawing` erstellt wurde — ein Verlauf von Hellgrau links zu Weiß rechts.

---

## Die Assets

Fünf statische PNGs liegen in `assets/images/`, eine Schriftart in `assets/fonts/`:

| Datei | Zweck |
| --- | --- |
| `og-bg.png` | 1200×630 Verlauf-Hintergrund |
| `og-badge.png` | Domain-Badge ("aws-sensei.cloud") |
| `og-btn.png` | "Read more"-Button |
| `og-btn-de.png` | "Weiterlesen"-Button für deutsche Posts |
| `og-photo-frame.png` | Weißer Rahmen hinter dem Foto |
| `og-photo-mask.png` | Rundet die Fotoecken ab |
| `sans-regular.ttf` | Inter Regular für die Textdarstellung |

Badge und Buttons werden mit PowerShells `System.Drawing` erstellt — damit lassen sich Pillenformen zeichnen, füllen und beschriften, ganz ohne externe Tools:

```powershell
Add-Type -AssemblyName System.Drawing

$font = New-Object System.Drawing.Font("Segoe UI", 15, [System.Drawing.FontStyle]::Bold)
$bmp  = New-Object System.Drawing.Bitmap($w, $h, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$g    = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

# Pillenform über GraphicsPath + AddArc
$path = New-Object System.Drawing.Drawing2D.GraphicsPath
$path.AddArc(0, 0, $r*2, $r*2, 180, 90)
# ... (restliche drei Ecken)
$path.CloseFigure()

$g.FillPath([System.Drawing.Brushes]::Black, $path)
$g.DrawString("Weiterlesen", $font, [System.Drawing.Brushes]::White, $rect, $sf)

$bmp.Save("og-btn-de.png", [System.Drawing.Imaging.ImageFormat]::Png)
```

Wichtig: Badge und Buttons sollten **gleich breit** sein. Den breitesten Text zuerst mit `MeasureString` messen, Padding addieren und diese Breite für alle Elemente verwenden.

---

## Das Template

Hugo lädt das OG-Template aus `layouts/partials/head/meta.html`. Das LoveIt-Theme hat eine eigene Version — eine Datei am selben Pfad im Projekt-Root überschreibt sie.

```go-html-template
{{- $bg      := resources.Get "images/og-bg.png" -}}
{{- $fontReg := resources.Get "fonts/sans-regular.ttf" -}}
{{- if and $bg $fontReg -}}
  {{- $canvas := $bg -}}

  {{- /* Foto mit weißem Rahmen und abgerundeten Ecken */ -}}
  {{- $frame := resources.Get "images/og-photo-frame.png" -}}
  {{- $mask  := resources.Get "images/og-photo-mask.png" -}}
  {{- with .Resources.GetMatch "featured-image*" -}}
    {{- $photo := .Fill "440x440 Center" -}}
    {{- if $frame -}}{{- $canvas = $canvas | images.Filter (images.Overlay $frame 35 90) -}}{{- end -}}
    {{- $canvas = $canvas | images.Filter (images.Overlay $photo 40 95) -}}
    {{- if $mask  -}}{{- $canvas = $canvas | images.Filter (images.Overlay $mask  40 95) -}}{{- end -}}
  {{- end -}}

  {{- /* Badge, Titel, sprachabhängiger Button */ -}}
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

## Was nicht funktioniert hat (und warum)

**Fette Schriften.** `images.Text` schlägt mit Inter Bold TTF und OTF lautlos fehl. Inter Regular funktioniert problemlos. Die eigentliche Ursache habe ich nie gefunden — der Wechsel zu Regular war die Lösung.

**Variablen in `range`-Schleifen.** Hugo's Go-Templates persistieren Variablenzuweisungen innerhalb von `range` nicht in den äußeren Scope, wie man es erwarten würde. Ich habe lange versucht, eine Wortumbruch-Logik zu bauen:

```go-html-template
{{- $l1 := "" -}}
{{- range split $.Title " " -}}
  {{- $l1 = printf "%s %s" $l1 . -}}  {{/* bleibt außerhalb der range nicht erhalten */}}
{{- end -}}
```

Am Ende stellte sich heraus: das war gar nicht nötig. `images.Text` **bricht Text automatisch am Canvas-Rand um**. Den vollen Titel als String übergeben — Hugo erledigt den Zeilenumbruch.

**`template.HTML` vs `string`.** Hugos `truncate` und einige andere String-Funktionen geben `template.HTML` zurück, keinen `string`. Das direkt an `images.Text` zu übergeben führt zu einem stillen Fehler. Mit `printf "%s"` konvertieren:

```go-html-template
{{- $canvas = $canvas | images.Filter
    (images.Text (printf "%s" $.Title) ...) -}}
```

**Abgerundete Fotoecken.** Der weiße Rahmen (`og-photo-frame.png`) und die Ecken-Maske (`og-photo-mask.png`) brauchen geometrisch abgestimmte Radien. Bei einem 5px-Rahmen und Außenradius `R` liegt die Fotoecke bei Position `(5, 5)` relativ zur Frame-Ecke. Dieser Punkt muss *innerhalb* des abgerundeten Bereichs liegen:

```text
sqrt((R-5)² + (R-5)²) ≤ R  →  R ≤ 17px
```

`radius=12` für den Frame und `radius=8` für die Maske funktionieren zuverlässig.

---

## Den Cache aus Git heraushalten

Hugo speichert verarbeitete Bild-Derivate in `resources/_gen/images/`. Diese Dateien sind inhaltsbasiert gehasht — ändert sich der Titel, ändern sich alle Hashes. Beim Committen entstehen laute Diffs.

In `.gitignore` eintragen:

```text
/frontend/resources/_gen/images/
```

Hugo regeneriert den Cache bei jedem Build. Für einen Blog mit ~15 Posts kostet das ein paar Sekunden mehr in der Pipeline — ein fairer Tausch.

---

## Ergebnis

Jeder Post bekommt jetzt ein 1200×630px-OG-Image, das zur Build-Zeit generiert wird:

- Korrekte Größe für WhatsApp, LinkedIn, Twitter/X
- Gebrandetes Domain-Badge
- Titel bricht automatisch um
- Deutsche Posts bekommen "Weiterlesen", englische "Read more"
- Null Runtime-Kosten — es sind nur statische Dateien auf S3

Was Hugo nicht kann: das Foto um einen beliebigen Winkel drehen (nur 90°-Schritte werden unterstützt). Dafür braucht man ein Build-Skript mit Pillow oder `@napi-rs/canvas`. Vielleicht ein zukünftiger Post.

---

{{< chat >}}
