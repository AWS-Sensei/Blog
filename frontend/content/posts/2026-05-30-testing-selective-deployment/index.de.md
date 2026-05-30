---
title: "Smarter deployen, sicher schlafen — Unit Tests und Change Detection für Lambda APIs"
date: 2026-05-30T00:00:00+02:00
lastmod: 2026-05-30T00:00:00+02:00
draft: false
author: "Marcel"
socialmedia: false
description: "Wie ich meine sieben Lambda-APIs mit Unit Tests abgesichert und die Pipeline so umgebaut habe, dass nur noch geänderte Services deployt werden — motiviert durch den Schritt in die Öffentlichkeit."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "CodePipeline", "CodeBuild", "Lambda", "Testing", "pytest", "CI/CD", "Python"]
lightgallery: true
---

{{< listen >}}

Solange ein Projekt nur für mich läuft, ist ein fehlgeschlagenes Deployment ärgerlich aber harmlos. Das ändert sich in dem Moment, in dem der erste LinkedIn-Post rausgeht und echte Leser auf die Seite kommen. Jetzt ist ein defektes Chat-Widget, ein kaputtes Kontaktformular oder eine ausgefallene Sentiment-Analyse nicht mehr nur ein persönliches Problem — es ist ein schlechter erster Eindruck.

Das war der Anlass, zwei Dinge anzugehen, die ich schon eine Weile vor mir hergeschoben hatte: **Unit Tests für alle Lambda-Funktionen** und eine **Pipeline, die nur noch das deployt was sich wirklich geändert hat**.

## Das Problem mit dem alten Ansatz

Meine APIs-Pipeline war simpel: jeder Push in `apis/**` → CodeBuild startet → alle sieben SAM-Stacks werden nacheinander deployt. Das klingt nach Plan, hat aber zwei Schwächen.

**Erstens: kein Sicherheitsnetz.** Keine einzige Zeile Test-Code. Ein Tippfehler im Handler, ein fehlerhafter Regex, eine falsch geparste Umgebungsvariable — alles landet direkt in Production. Das war für ein Lernprojekt akzeptabel, für ein öffentlich verlinktes Projekt nicht mehr.

**Zweitens: unnötige Kosten und Wartezeit.** Ändere ich etwas am Social-Service, deployen trotzdem alle sieben APIs. Das dauert länger und kostet mehr CodeBuild-Minuten als nötig — im schlechtesten Fall 85% davon für Services, die gar nicht angefasst wurden.

## Lösung Teil 1 — Change Detection per Hash

Die naheliegende Idee wäre `git diff`, aber CodeBuild bekommt den Source standardmäßig als S3-Artifact ohne vollständige Git-History. Statt dieses Problem zu lösen, habe ich einen anderen Weg gewählt: **Hash-basierte Change Detection via SSM Parameter Store**.

Das Prinzip ist einfach: vor jedem Deploy berechne ich für jeden Service einen SHA256-Hash über alle `.py`-Dateien und das `template.yaml`. Diesen Hash vergleiche ich mit dem zuletzt gespeicherten Wert in SSM (`/sensei/deploy-hash/{service}`). Nur wenn sich etwas geändert hat, wird getestet und deployt — und nach erfolgreichem Deploy wird der neue Hash gespeichert.

```bash
HASH=$(find apis/$service -type f \( -name "*.py" -o -name "template.yaml" \) \
       | sort | xargs sha256sum | sha256sum | cut -d' ' -f1)
STORED=$(aws ssm get-parameter --name "/sensei/deploy-hash/$service" \
         --query "Parameter.Value" --output text 2>/dev/null || echo "none")

if [ "$HASH" != "$STORED" ]; then
  echo "$service: changed — will test and deploy"
fi
```

Das Schöne daran: der Buildspec ist komplett **generisch**. Neue APIs werden automatisch erkannt sobald sie ein `template.yaml` haben — ich muss die Pipeline nie anfassen.

```bash
for template in apis/*/template.yaml; do
  service=$(basename $(dirname $template))
  # hash, compare, test, deploy...
done
```

## Lösung Teil 2 — Unit Tests mit pytest

Alle sieben Lambda-Funktionen sind in Python 3.12 geschrieben und nutzen ausschließlich boto3. Das macht das Test-Setup angenehm schlank: kein eigener Testserver, keine Datenbank, nur Python und die Standardbibliothek.

Statt moto (AWS-Mock-Framework) habe ich `unittest.mock` aus der Standardbibliothek gewählt — es ist direkter und braucht keine zusätzlichen Dependencies. Der Trick: boto3-Clients die auf Modul-Ebene erstellt werden, lassen sich über `patch.object` ersetzen.

```python
# handler.py
ses = boto3.client("ses", region_name="eu-central-1")

def lambda_handler(event, context):
    ses.send_email(...)
```

```python
# test_handler.py
@patch.object(handler, "ses")
def test_valid_request_sends_email(mock_ses):
    handler.lambda_handler(event({...}), {})
    mock_ses.send_email.assert_called_once()
```

Der boto3-Client im Handler zeigt jetzt auf den Mock — keine echten AWS-Calls, keine Credentials nötig, läuft in unter einer Sekunde.

### conftest.py als sauberer Einstiegspunkt

Jeder Service bekommt ein `tests/`-Verzeichnis mit einer `conftest.py`. pytest lädt diese Datei automatisch vor allen Tests — ideal für den `sys.path`-Setup und Umgebungsvariablen:

```python
# apis/contact/tests/conftest.py
import sys, os
os.environ["TO_EMAIL"] = "to@example.com"
os.environ["FROM_EMAIL"] = "from@example.com"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
```

Die Testdatei selbst ist dann frei von Setup-Code und enthält nur Tests.

### Services mit mehreren Handlers

Der `cost`-Service hat zwei unabhängige Handler: `read` (liest gecachte Daten aus SSM) und `refresh` (ruft Cost Explorer ab und speichert). Da beide `handler.py` heißen würden, gibt es einen Namenskonflikt in `sys.modules`.

Die Lösung: **Subdirectories analog zu `src/`**, kombiniert mit `__init__.py` damit pytest sie als separate Packages behandelt:

```tezt
apis/cost/
├── src/
│   ├── read/handler.py
│   └── refresh/handler.py
└── tests/
    ├── read/
    │   ├── __init__.py
    │   ├── conftest.py    ← lädt src/read/handler.py via importlib
    │   └── test_handler.py
    └── refresh/
        ├── __init__.py
        ├── conftest.py    ← lädt src/refresh/handler.py via importlib
        └── test_handler.py
```

## Lösung Teil 3 — sprachunabhängiger Test-Runner

Um den Buildspec nicht auf Python festzunageln, bekommt jeder Service ein `tests/run.sh`. Der Buildspec ruft nur noch dieses Script auf:

```yaml
# apis/buildspec.yml (Auszug)
- |
  for service in $CHANGED_SERVICES; do
    if [ -f "apis/$service/tests/run.sh" ]; then
      bash apis/$service/tests/run.sh
    fi
  done
```

Ein Python-Service sieht dann so aus:

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")/.."
pip3 install -q -r tests/requirements-test.txt
python3 -m pytest tests/ -v --tb=short
```

Ein zukünftiger Node.js-Service würde einfach `npm ci && npm test` aufrufen. Die Pipeline bleibt unverändert.

## Wie es zusammenspielt

Der vollständige Ablauf bei einem Push in `apis/**`:

```text
pre_build:  Hash-Vergleich für alle Services
            → CHANGED_SERVICES = "social"

build:      bash apis/social/tests/run.sh
            → pytest: 11 passed
            sam deploy --stack-name sensei-api-social ...
            → Deploy erfolgreich
            aws ssm put-parameter /sensei/deploy-hash/social ...
            → Hash aktualisiert
```

Schlägt ein Test fehl, bricht die Pipeline ab — kein Deploy passiert. Sind alle Tests grün, deployt nur der eine geänderte Service.

## Ergebnis

- **7 Services**, alle mit Unit Tests abgedeckt
- **Typischer Push**: 1 Service deployt statt 7 (~85% weniger CodeBuild-Minuten)
- **Pipeline bleibt generisch**: neue APIs werden automatisch erkannt
- **Kein Framework-Lock-in**: jeder Service wählt seinen eigenen Test-Runner

Das ist kein perfektes Setup — Integrationstests fehlen noch, und die Hash-Methode merkt nicht wenn sich nur ein Kommentar geändert hat. Aber für ein Projekt in dieser Phase ist es eine solide Basis: schnelles Feedback, weniger Kosten, und ein Sicherheitsnetz das tatsächlich eingreift bevor etwas in Production landet.
