---
title: "Smarter S3 Triggers: Hash Files, SNS Fanout, and No More Redundant Calls"
date: 2026-05-22T00:00:00+02:00
lastmod: 2026-05-22T00:00:00+02:00
draft: false
author: "Marcel"
description: "How a 0-byte file with an MD5 hash in its name fixes the KMS ETag problem, eliminates redundant Lambda invocations, and opens the door for an SNS-based event fan-out."
images: []
tags: ["AWS", "Lambda", "S3", "SNS", "Serverless", "CI/CD"]
lightgallery: true
---

{{< listen >}}

The [Polly TTS setup](/posts/2026-04-30-polly-tts/) worked well, but there was a flaw: every deployment triggered the Polly Lambda for every post, even when nothing had changed. The Lambda's content-hash check caught duplicates after the fact, but the invocations still happened for all posts on every push. At the AWS Summit in Hamburg on May 20th I had some time to think through a cleaner solution.

---

## The Root Cause

The S3 bucket uses SSE-KMS encryption. When S3 stores an object with KMS, the ETag is derived from the *encrypted* content — not the plaintext. `aws s3 sync` compares the local MD5 against the KMS-modified ETag in S3, they never match, and every markdown file gets re-uploaded on every deployment — regardless of whether the content changed.

Every upload fires an S3 event. Every event invokes the Lambda.

---

## Hash in the Filename

The fix moves deduplication to the trigger file itself. Instead of syncing the markdown files directly, the pipeline computes an MD5 hash of each post's content and creates a 0-byte file named after that hash:

```bash
hash=$(md5sum "$md_file" | cut -d' ' -f1)
touch "/tmp/post-triggers/$slug/index.$lang.$hash"
```

`aws s3 sync --size-only --delete` does the rest:

- **Same content** → same hash → same filename → already in S3 → skipped, no event fired
- **Changed content** → new hash → new filename → uploaded → S3 event → Lambda invoked
- **`--delete`** removes the old hash file when a post changes, keeping exactly one trigger file per post in S3

The `--size-only` flag is needed because all trigger files are 0 bytes — without it, the KMS ETag mismatch would cause every trigger file to be re-uploaded on every deploy, defeating the purpose.

The Lambda itself never reads the trigger file. It only extracts the slug and language from the key path to locate the rendered HTML in S3.

---

## SNS Fanout

While rethinking the trigger, a second problem became obvious: the S3 bucket notification pointed directly at the Polly Lambda ARN. This created a deployment chicken-and-egg — the Lambda had to exist before the S3 bucket could be fully configured, which meant managing a `HasPolly` condition in the infrastructure stack.

More practically: adding a second consumer (a Lambda that shares new posts to LinkedIn, for example) would mean modifying the S3 notification config every time.

The fix: S3 publishes to an SNS topic instead. Lambdas subscribe independently.

```text
S3 (_content/posts/) → SNS sensei-post-changed → Polly Lambda
                                                → LinkedIn Lambda (soon)
```

The SNS topic belongs to the core infrastructure stack. Consumer Lambdas subscribe on their own — no cross-stack dependency, no chicken-and-egg.

---

## Idempotency

SNS Standard delivers at-least-once. If the same event arrives twice, the Lambda would call Polly twice for the same content.

The existing content-hash check — originally written to handle the KMS re-upload problem — doubles as an idempotency guard:

```python
content_hash = hashlib.md5(text.encode()).hexdigest()

head = s3.head_object(Bucket=BUCKET, Key=audio_key)
if head.get("Metadata", {}).get("content-hash") == content_hash:
    print(f"Content unchanged, skipping: {audio_key}")
    return
```

If the same message is delivered twice, the second invocation computes the same hash, finds it already stored in S3 metadata, and exits without touching Polly. The original fix for the KMS problem now handles SNS at-least-once delivery for free.

---

{{< chat >}}
