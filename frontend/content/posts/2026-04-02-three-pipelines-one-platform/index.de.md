---
title: "Drei Pipelines, eine Plattform — meine CI/CD-Architektur auf AWS"
date: 2026-04-02T00:00:00+02:00
lastmod: 2026-04-02T00:00:00+02:00
draft: false
author: "Marcel"
description: "Wie ich meinen Blog von einer einzigen Pipeline auf drei getrennte AWS CodePipelines (V2) mit Pfad-Filtern umgebaut habe — für Frontend, Infrastruktur und APIs."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "CodePipeline", "CodeBuild", "SAM", "IaC", "CI/CD", "CloudFormation"]
lightgallery: true
---

Im [ersten Post](/de/posts/2026-03-26-aws-cloud-migration-blog/) habe ich beschrieben wie aws-sensei.cloud grundsätzlich aufgebaut ist — Hugo, S3, CloudFront, eine CodeBuild-Pipeline. Das war ein guter Anfang. Aber eine Pipeline für alles skaliert nicht.

Das Problem zeigt sich in der Praxis schneller als erwartet: Mit einer einzigen Pipeline bin ich beim Schreiben von Blog Posts regelmäßig an das Free-Tier-Limit von CodeBuild gestoßen — obwohl ich nur Markdown geändert hatte. Jeder Commit triggerte die komplette Pipeline: Hugo-Build, Infrastruktur-Deploy, alles. Das ist weder effizient noch kostenfreundlich.

Dazu kommt die logische Trennung: Ein Tippfehler im Blogartikel sollte nicht die Infrastruktur neu deployen. Eine Lambda-Änderung sollte nicht den Hugo-Build triggern. Je mehr dazukommt, desto wichtiger wird eine saubere Trennung.

## Die neue Repo-Struktur

Alles lebt in einem Repository — aber sauber aufgeteilt:

```text
Blog/
├── frontend/          ← Hugo-Blog (HTML, Markdown, Theme)
│   └── buildspec.yml
├── apis/              ← Lambda-Funktionen (kommt bald)
│   └── buildspec.yml
├── infra/             ← CloudFormation-Templates
│   └── infrastructure.yaml
└── shared/            ← Gemeinsame Utilities (z.B. Lambda Layers)
```

Drei Ordner, drei Verantwortlichkeiten, drei Pipelines — jede triggert nur wenn ihr Ordner sich ändert.

## CodePipeline V2 mit Pfad-Filtern

Das war der entscheidende Schritt. CodePipeline V2 unterstützt native Pfad-Filter direkt in CloudFormation:

```yaml
AWSSenseiBlogPipeline:
  Type: AWS::CodePipeline::Pipeline
  Properties:
    PipelineType: V2
    Triggers:
      - ProviderType: CodeStarSourceConnection
        GitConfiguration:
          SourceActionName: GitHub_Source
          Push:
            - FilePaths:
                Includes:
                  - frontend/**
```

Mit V1 gab es diese Möglichkeit nicht. Der Workaround wäre ein CodeBuild-Step am Anfang der Pipeline gewesen, der per `git diff` prüft ob der relevante Ordner geändert wurde — und bei Bedarf früh abbricht. V2 macht das überflüssig.

## Pipeline 1 — Frontend

![Frontend Pipeline](frontend-pipeline.png)

```text
GitHub (frontend/**) → Hugo Build → S3 Sync → CloudFront Invalidate
```

Der Hugo-Build läuft in CodeBuild mit der `frontend/buildspec.yml`. Die Umgebungsvariablen `WEBSITE_BUCKET` und `CLOUDFRONT_DISTRIBUTION_ID` kommen nicht mehr aus der Pipeline selbst — sie werden zur Laufzeit aus dem **SSM Parameter Store** gelesen:

```yaml
EnvironmentVariables:
  - Name: WEBSITE_BUCKET
    Type: PARAMETER_STORE
    Value: /sensei/blog/bucket-name
  - Name: CLOUDFRONT_DISTRIBUTION_ID
    Type: PARAMETER_STORE
    Value: /sensei/blog/cloudfront-distribution-id
```

Die Parameter selbst werden von der Infra-Pipeline automatisch aktualisiert — dazu gleich mehr.

Eine Randnotiz: SSM-Parameter-Namen dürfen nicht mit `/aws` beginnen — das ist ein von AWS reservierter Namespace. `/sensei/` funktioniert problemlos.

## Pipeline 2 — Infrastruktur

![Infra Pipeline](infra-pipeline.png)

```text
GitHub (infra/**) → Manual Approval → CloudFormation Deploy
```

Infrastruktur-Änderungen sind gefährlicher als Lambda-Code oder Blog-Texte. Ein manueller Approval-Step vor dem Deploy gibt die nötige Kontrolle:

```yaml
- Name: ManualApproval
  Actions:
    - Name: Approve_Infra_Deploy
      ActionTypeId:
        Category: Approval
        Owner: AWS
        Provider: Manual
        Version: "1"
```

Das CloudFormation-Template (`infra/infrastructure.yaml`) definiert S3-Bucket, CloudFront-Distribution, Route53-Record und ACM-Zertifikat. Nach jedem erfolgreichen Deploy schreibt CloudFormation die aktuellen Werte automatisch in den SSM Parameter Store:

```yaml
WebsiteBucketNameParam:
  Type: AWS::SSM::Parameter
  DeletionPolicy: Retain
  Properties:
    Name: /sensei/blog/bucket-name
    Value: !Ref WebsiteBucket
```

So sind Frontend-Pipeline und Infra-Pipeline vollständig entkoppelt — keine hardcodierten Werte, keine gemeinsamen Abhängigkeiten zur Deployment-Zeit.

## Pipeline 3 — APIs

![APIs Pipeline](apis-pipeline.png)

```text
GitHub (apis/**) → SAM Deploy (alle Stacks)
```

Diese Pipeline ist für alle Lambda-Funktionen und API Gateways zuständig — die in den kommenden Posts entstehen werden. Jedes Feature bekommt seinen eigenen Ordner mit einem SAM-Template:

```text
apis/
├── sentiment/
│   ├── handler.py
│   ├── requirements.txt
│   └── template.yaml
└── buildspec.yml
```

Das `buildspec.yml` iteriert dynamisch über alle vorhandenen Templates:

```bash
for template in apis/*/template.yaml; do
  stack_name="sensei-api-$(basename $(dirname $template))"
  sam deploy \
    --template-file $template \
    --stack-name $stack_name \
    --no-fail-on-empty-changeset
done
```

Neues Feature = neuer Ordner. Die Pipeline muss nie angefasst werden.

## Die CICD-Infrastruktur selbst

Die drei Pipelines, CodeBuild-Projekte und IAM-Rollen sind selbst als CloudFormation definiert — in einem separaten Repository (`AWS-Sensei/Infrastructure`). Ein `master.yaml` orchestriert alles als Nested Stacks:

```text
master.yaml
├── foundation/roles.yaml       ← IAM Roles
├── foundation/artifacts.yaml   ← S3 Artifact Bucket
├── build/codebuild.yaml        ← Hugo CodeBuild
├── build/sam-codebuild.yaml    ← SAM CodeBuild
├── pipeline/pipeline.yaml      ← Frontend Pipeline
├── pipeline/infra-pipeline.yaml ← Infra Pipeline
└── pipeline/apis-pipeline.yaml  ← APIs Pipeline
```

Infrastructure as Code bis zur letzten Schraube.

## Was als nächstes kommt

Die APIs-Pipeline ist bereit — ihr erstes Feature ist bereits live: ein **Sentiment-Analyse Widget** mit AWS Comprehend. Besucher tippen einen Satz ein und sehen in Echtzeit ob er positiv, negativ oder neutral klingt. Wie es gebaut wurde, beschreibt der [nächste Post](/de/posts/2026-04-27-sentiment-widget/).
