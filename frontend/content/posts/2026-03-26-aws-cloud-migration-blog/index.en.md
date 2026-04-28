---
title: "From Vercel to AWS — Migrating My Blog to the Cloud"
date: 2026-03-26T00:00:00+02:00
lastmod: 2026-03-26T00:00:00+02:00
draft: false
author: "Marcel"
description: "Why I moved my Vue blog from Vercel and rebuilt it with Hugo, S3, CloudFront, and a fully automated CodeBuild pipeline — as Infrastructure as Code."

images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"

tags: ["AWS", "Hugo", "CloudFront", "S3", "CodeBuild", "IaC", "Migration", "Vercel"]

lightgallery: true
---

I have been working with AWS for over six years — in projects, in architecture, day to day. At some point it became clear: if I take my AWS knowledge seriously and want to show it to the world, my own infrastructure should reflect that.

That is how **AWS Sensei** came about — as a platform to share knowledge, try things out, and make AWS skills visible. And if you are advertising your AWS skills, your own blog should run on AWS too.

Before the migration, the blog ran as a Vue application on Vercel. Vercel is great — quick to set up, free for small projects, zero ops overhead. But it is simply not AWS. No IAM roles, no CloudFormation templates, no pipeline I control myself. For a pure hobby blog that would not be a problem — for a portfolio meant to demonstrate AWS competence, it is.

The migration was also a good opportunity to simplify the stack: out with Vue, in with **Hugo**. A static site generator without build complexity, without Node dependencies, without running processes. Markdown in, static HTML out.

## Why Hugo?

I chose **Hugo** — not because of the theme or the community, but because of speed. Hugo builds hundreds of pages in milliseconds. That shows in the CI/CD pipeline when you want fast feedback. And unlike Vue, there is no build process that needs maintenance — no npm updates, no breaking changes in dependencies.

The theme I use is **LoveIt** — it supports dark mode, syntax highlighting, multilingual content, and is lean enough to customize when needed.

## Infrastructure Overview

```text
Browser → Route53 → CloudFront → S3
                        ↑
                  ACM Certificate
                  (TLS 1.2+)
```

Four AWS services, all defined as Infrastructure as Code in a single SAM template.

### S3 — Accessible Only via CloudFront

The S3 bucket holds the generated HTML files. Public access is completely blocked. Only CloudFront is allowed to read objects — enforced via **Origin Access Control (OAC)**, the modern successor to OAI:

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

The key difference from OAI: the permission is bound to a specific CloudFront distribution, not a generic identity. This makes unintentional cross-distribution access impossible.

### CloudFront — CDN, HTTPS, and URL Rewriting

CloudFront handles three things:

1. **Enforce HTTPS** — HTTP requests are automatically redirected to HTTPS.
2. **Caching** — Static files are cached at edge locations worldwide.
3. **URL Rewriting** — Hugo generates `posts/my-article/index.html`. When a browser requests `/posts/my-article/`, CloudFront needs to translate the trailing slash into `index.html`. A small **CloudFront Function** handles this:

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

This function runs at the edge — no Lambda cold start, no noticeable latency.

### Route53 and ACM

An alias record in Route53 points directly to the CloudFront distribution. The ACM certificate must be in `us-east-1` — a CloudFront requirement, regardless of where the rest of the infrastructure runs.

## CI/CD Pipeline with CodeBuild

A `git push` to the main branch automatically triggers a CodeBuild pipeline. All build logic lives in a `buildspec.yml`:

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

Three phases:

- **Install** — Hugo Extended is downloaded directly from GitHub. No pre-installed tools needed.
- **Build** — `hugo --minify` generates the complete static HTML with optimized assets.
- **Post-Build** — The generated files are synced to the bucket via `aws s3 sync`. The `--delete` flag removes files that no longer exist. Afterwards, the CloudFront cache is invalidated so visitors immediately see the new version.

The environment variables `WEBSITE_BUCKET` and `CLOUDFRONT_DISTRIBUTION_ID` come from the CodeBuild project itself — not from the code.

## Multilingual Support in Hugo

All content exists twice — as `index.de.md` and `index.en.md` in the same folder. Hugo detects the language from the filename and builds both versions automatically. In `hugo.toml`, each language is configured with its own menu and profile text.

Switching between DE and EN happens via a language switcher in the theme — no JavaScript, purely static links.

---

{{< chat >}}
