---
title: "Von Vercel zu AWS — Migration meines Blogs in die Cloud"
date: 2026-03-26T00:00:00+02:00
draft: false
author: "Marcel"
description: "Warum ich meinen Vue-Blog auf Vercel aufgegeben und ihn mit Hugo, S3, CloudFront und einer vollautomatischen CodeBuild-Pipeline auf AWS neu aufgebaut habe — als Infrastructure as Code."

images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"

tags: ["AWS", "Hugo", "CloudFront", "S3", "CodeBuild", "IaC", "Migration", "Vercel"]

lightgallery: true
---

{{< listen >}}

Ich arbeite seit über sechs Jahren mit AWS — in Projekten, in der Architektur, im Alltag. Irgendwann war klar: Wenn ich mein AWS-Wissen ernst nehme und nach außen zeigen will, sollte meine eigene Infrastruktur das widerspiegeln.

So ist **AWS Sensei** entstanden — als Plattform um Wissen zu teilen, Dinge auszuprobieren und AWS-Kenntnisse sichtbar zu machen. Und wer mit seinen AWS-Skills wirbt, sollte seinen eigenen Blog auch auf AWS betreiben.

Vorher lief der Blog als Vue-Anwendung auf Vercel. Vercel ist gut — schnell eingerichtet, kostenlos für kleine Projekte, kein Ops-Aufwand. Aber es ist eben nicht AWS. Keine IAM-Rollen, keine CloudFormation-Templates, keine Pipeline die ich selbst kontrolliere. Für einen reinen Hobby-Blog wäre das kein Problem — für ein Portfolio das AWS-Kompetenz demonstrieren soll, schon.

Die Migration war auch eine gute Gelegenheit den Stack zu vereinfachen: raus aus Vue, rein in **Hugo**. Ein Static Site Generator ohne Build-Komplexität, ohne Node-Dependencies, ohne laufende Prozesse. Markdown rein, statisches HTML raus.

## Warum Hugo?

Ich habe mich für **Hugo** entschieden — nicht wegen des Themes oder der Community, sondern wegen der Geschwindigkeit. Hugo baut hunderte Seiten in Millisekunden. Das macht sich in der CI/CD-Pipeline bemerkbar, wenn man schnelles Feedback will. Und im Gegensatz zu Vue gibt es keinen Build-Prozess der gewartet werden muss — keine npm-Updates, keine Breaking Changes in Abhängigkeiten.

Das verwendete Theme ist **LoveIt** — es unterstützt Dark Mode, Syntax-Highlighting, mehrsprachige Inhalte und ist schlank genug um es bei Bedarf anzupassen.

## Die Infrastruktur im Überblick

```text
Browser → Route53 → CloudFront → S3
                        ↑
                  ACM-Zertifikat
                  (TLS 1.2+)
```

Vier AWS-Services, alle als Infrastructure as Code in einer einzigen SAM-Vorlage definiert.

### S3 — Nur für CloudFront zugänglich

Das S3-Bucket enthält die generierten HTML-Dateien. Öffentlicher Zugriff ist vollständig gesperrt. Nur CloudFront darf Objekte lesen — geregelt über **Origin Access Control (OAC)**, der moderneren Nachfolge von OAI:

```yaml
WebsiteBucketPolicy:
  Type: AWS::S3::BucketPolicy
  Properties:
    PolicyDocument:
      Statement:
        - Effect: Allow
          Principal:
            Service: cloudfront.amazonaws.com
          Action: s3:GetObject
          Resource: !Sub "${WebsiteBucket.Arn}/*"
          Condition:
            StringEquals:
              AWS:SourceArn: !Sub "arn:aws:cloudfront::${AWS::AccountId}:distribution/${CloudFrontDistribution}"
```

Der entscheidende Unterschied zu OAI: Die Berechtigung ist an eine konkrete CloudFront-Distribution gebunden, nicht an eine generische Identity. Das macht unbeabsichtigten Cross-Distribution-Zugriff unmöglich.

### CloudFront — CDN, HTTPS und URL-Rewriting

CloudFront übernimmt drei Aufgaben:

1. **HTTPS erzwingen** — HTTP-Anfragen werden automatisch auf HTTPS umgeleitet.
2. **Caching** — Statische Dateien werden weltweit an Edge-Locations zwischengespeichert.
3. **URL-Rewriting** — Hugo generiert `posts/mein-artikel/index.html`. Ruft ein Browser `/posts/mein-artikel/` auf, muss CloudFront den Slash am Ende in `index.html` übersetzen. Das übernimmt eine kleine **CloudFront Function**:

```javascript
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.endsWith('/')) {
    request.uri += 'index.html';
  }
  return request;
}
```

Diese Funktion läuft an der Edge — ohne Lambda-Kaltstart, ohne spürbare Latenz.

### Route53 und ACM

Ein Alias-Record in Route53 zeigt direkt auf die CloudFront-Distribution. Das ACM-Zertifikat muss in `us-east-1` liegen — eine Anforderung von CloudFront, unabhängig davon wo der Rest der Infrastruktur betrieben wird.

## Die CI/CD-Pipeline mit CodeBuild

Ein `git push` auf den Main-Branch löst automatisch eine CodeBuild-Pipeline aus. Die gesamte Build-Logik steckt in einer `buildspec.yml`:

```yaml
phases:
  install:
    commands:
      - curl -L https://github.com/gohugoio/hugo/releases/download/v${HUGO_VERSION}/hugo_extended_${HUGO_VERSION}_Linux-64bit.tar.gz -o hugo.tar.gz
      - tar -xzf hugo.tar.gz
      - mv hugo /usr/local/bin/

  build:
    commands:
      - cd blog
      - hugo --minify

  post_build:
    commands:
      - aws s3 sync public/ s3://$WEBSITE_BUCKET --delete
      - aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DISTRIBUTION_ID --paths "/*"
```

Drei Phasen:

- **Install** — Hugo Extended wird direkt von GitHub heruntergeladen. Keine vorinstallierten Tools nötig.
- **Build** — `hugo --minify` generiert das komplette statische HTML mit optimierten Assets.
- **Post-Build** — Die generierten Dateien landen per `aws s3 sync` im Bucket. Das `--delete` Flag entfernt Dateien die nicht mehr existieren. Anschließend wird der CloudFront-Cache invalidiert, damit Besucher sofort die neue Version sehen.

Die Umgebungsvariablen `WEBSITE_BUCKET` und `CLOUDFRONT_DISTRIBUTION_ID` kommen aus dem CodeBuild-Projekt selbst — nicht aus dem Code.

## Zweisprachigkeit in Hugo

Alle Inhalte existieren zweimal — als `index.de.md` und `index.en.md` im selben Ordner. Hugo erkennt die Sprache anhand des Dateinamens und baut beide Versionen automatisch. In `hugo.toml` ist jede Sprache mit eigenem Menü und eigenem Profil-Text konfiguriert.

Das Umschalten zwischen DE und EN erfolgt über einen Sprachumschalter im Theme — ohne JavaScript, rein über statische Links.

---

{{< chat >}}
