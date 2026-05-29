---
title: "Deploy smarter, sleep better — unit tests and change detection for Lambda APIs"
date: 2026-05-30T00:00:00+02:00
lastmod: 2026-05-30T00:00:00+02:00
draft: true
author: "Marcel"
socialmedia: false
description: "How I added unit tests to all seven Lambda APIs and rebuilt the pipeline to only deploy services that actually changed — motivated by going public on LinkedIn."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"
tags: ["AWS", "CodePipeline", "CodeBuild", "Lambda", "Testing", "pytest", "CI/CD", "Python"]
lightgallery: true
---

{{< listen >}}

As long as a project runs only for me, a failed deployment is annoying but harmless. That changes the moment the first LinkedIn post goes out and real readers land on the site. A broken chat widget, a dead contact form, or a failed sentiment analysis is no longer just a personal problem — it's a bad first impression.

That was the trigger to tackle two things I'd been putting off: **unit tests for all Lambda functions** and a **pipeline that only deploys what actually changed**.

## The problem with the old approach

My APIs pipeline was simple: any push to `apis/**` → CodeBuild starts → all seven SAM stacks deploy one by one. That sounds fine, but it had two weaknesses.

**First: no safety net.** Not a single line of test code. A typo in a handler, a broken regex, a misread environment variable — everything landed directly in production. Acceptable for a learning project, not for something publicly linked.

**Second: unnecessary cost and wait time.** Change something in the social service, and all seven APIs deploy anyway. That takes longer and burns more CodeBuild minutes than necessary — in the worst case, 85% of them for services that weren't touched at all.

## Solution part 1 — change detection via hash

The obvious idea would be `git diff`, but CodeBuild receives the source as an S3 artifact without full Git history by default. Instead of solving that problem, I went a different route: **hash-based change detection via SSM Parameter Store**.

The principle is simple: before each deploy I compute a SHA256 hash over all `.py` files and the `template.yaml` for each service. I compare this hash against the last stored value in SSM (`/sensei/deploy-hash/{service}`). Only when something changed does the service get tested and deployed — and after a successful deploy the new hash is stored.

```bash
HASH=$(find apis/$service -type f \( -name "*.py" -o -name "template.yaml" \) \
       | sort | xargs sha256sum | sha256sum | cut -d' ' -f1)
STORED=$(aws ssm get-parameter --name "/sensei/deploy-hash/$service" \
         --query "Parameter.Value" --output text 2>/dev/null || echo "none")

if [ "$HASH" != "$STORED" ]; then
  echo "$service: changed — will test and deploy"
fi
```

The nice part: the buildspec is completely **generic**. New APIs are picked up automatically as soon as they have a `template.yaml` — I never need to touch the pipeline.

```bash
for template in apis/*/template.yaml; do
  service=$(basename $(dirname $template))
  # hash, compare, test, deploy...
done
```

## Solution part 2 — unit tests with pytest

All seven Lambda functions are written in Python 3.12 and use only boto3. That makes the test setup pleasantly lean: no test server, no database, just Python and the standard library.

Instead of moto (AWS mock framework) I chose `unittest.mock` from the standard library — it's more direct and needs no additional dependencies. The trick: boto3 clients created at module level can be replaced via `patch.object`.

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

The boto3 client in the handler now points to the mock — no real AWS calls, no credentials needed, runs in under a second.

### conftest.py as a clean entry point

Each service gets a `tests/` directory with a `conftest.py`. pytest loads this file automatically before all tests — ideal for `sys.path` setup and environment variables:

```python
# apis/contact/tests/conftest.py
import sys, os
os.environ["TO_EMAIL"] = "to@example.com"
os.environ["FROM_EMAIL"] = "from@example.com"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
```

The test file itself is then free of setup code and contains only tests.

### Services with multiple handlers

The `cost` service has two independent handlers: `read` (reads cached data from SSM) and `refresh` (calls Cost Explorer and stores the result). Since both would be named `handler.py`, there's a naming conflict in `sys.modules`.

The solution: **subdirectories mirroring `src/`**, combined with `__init__.py` so pytest treats them as separate packages:

```text
apis/cost/
├── src/
│   ├── read/handler.py
│   └── refresh/handler.py
└── tests/
    ├── read/
    │   ├── __init__.py
    │   ├── conftest.py    ← loads src/read/handler.py via importlib
    │   └── test_handler.py
    └── refresh/
        ├── __init__.py
        ├── conftest.py    ← loads src/refresh/handler.py via importlib
        └── test_handler.py
```

## Solution part 3 — language-agnostic test runner

To avoid locking the buildspec to Python, each service gets a `tests/run.sh`. The buildspec only calls this script:

```yaml
# apis/buildspec.yml (excerpt)
- |
  for service in $CHANGED_SERVICES; do
    if [ -f "apis/$service/tests/run.sh" ]; then
      bash apis/$service/tests/run.sh
    fi
  done
```

A Python service looks like this:

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")/.."
pip3 install -q -r tests/requirements-test.txt
python3 -m pytest tests/ -v --tb=short
```

A future Node.js service would simply call `npm ci && npm test`. The pipeline stays unchanged.

## How it fits together

The full flow on a push to `apis/**`:

```text
pre_build:  Hash comparison for all services
            → CHANGED_SERVICES = "social"

build:      bash apis/social/tests/run.sh
            → pytest: 11 passed
            sam deploy --stack-name sensei-api-social ...
            → Deploy successful
            aws ssm put-parameter /sensei/deploy-hash/social ...
            → Hash updated
```

If a test fails, the pipeline stops — no deploy happens. Once all tests are green, only the one changed service deploys.

## Results

- **7 services**, all covered with unit tests
- **Typical push**: 1 service deployed instead of 7 (~85% fewer CodeBuild minutes)
- **Pipeline stays generic**: new APIs are detected automatically
- **No framework lock-in**: each service picks its own test runner

This isn't a perfect setup — integration tests are still missing, and the hash method won't notice a comment-only change. But for a project at this stage it's a solid foundation: fast feedback, lower cost, and a safety net that actually catches issues before they reach production.
