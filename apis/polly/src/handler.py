import boto3
import os
import re
from html.parser import HTMLParser

BUCKET = os.environ["WEBSITE_BUCKET"]

VOICES = {
    "en": "Matthew",
    "de": "Daniel",
}

CODE_LABEL = {
    "en": "Code example.",
    "de": "Codebeispiel.",
}


class ArticleExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_article = False
        self.article_depth = 0
        self.skip_tags = {"pre", "script", "style", "nav", "header", "footer"}
        self.skip_depth = 0
        self.in_pre = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "article":
            self.in_article = True
            self.article_depth += 1
        elif self.in_article:
            if tag == "pre":
                self.in_pre = True
            elif tag in self.skip_tags:
                self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag == "article" and self.in_article:
            self.article_depth -= 1
            if self.article_depth == 0:
                self.in_article = False
        elif self.in_article:
            if tag == "pre":
                self.in_pre = False
            elif tag in self.skip_tags:
                self.skip_depth -= 1

    def handle_data(self, data):
        if self.in_article and not self.in_pre and self.skip_depth == 0:
            self.parts.append(data)

    def get_text(self):
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def inject_code_labels(html_content, label):
    return re.sub(
        r"<pre[\s\S]*?</pre>",
        f" {label} ",
        html_content,
        flags=re.IGNORECASE,
    )


def split_text(text, max_chars=2900):
    chunks = []
    while len(text) > max_chars:
        idx = max_chars
        for sep in [". ", "! ", "? ", "\n", " "]:
            pos = text.rfind(sep, 0, max_chars)
            if pos > 100:
                idx = pos + len(sep)
                break
        chunks.append(text[:idx])
        text = text[idx:]
    if text:
        chunks.append(text)
    return chunks


def lambda_handler(event, context):
    s3 = boto3.client("s3", region_name="eu-central-1")
    polly = boto3.client("polly", region_name="eu-central-1")

    record = event["Records"][0]
    key = record["s3"]["object"]["key"]
    # key: _content/posts/{slug}/index.{lang}.md
    parts = key.split("/")
    slug = parts[2]
    lang = parts[3].split(".")[1]  # en or de

    if lang not in VOICES:
        print(f"Unsupported language: {lang}")
        return

    html_key = f"posts/{slug}/index.html" if lang == "en" else f"{lang}/posts/{slug}/index.html"

    try:
        response = s3.get_object(Bucket=BUCKET, Key=html_key)
        html_content = response["Body"].read().decode("utf-8")
    except Exception as e:
        print(f"HTML not found: {html_key} — {e}")
        return

    html_content = inject_code_labels(html_content, CODE_LABEL[lang])

    extractor = ArticleExtractor()
    extractor.feed(html_content)
    text = extractor.get_text()

    if not text:
        print(f"No text extracted from {html_key}")
        return

    chunks = split_text(text)
    audio_parts = []

    for chunk in chunks:
        resp = polly.synthesize_speech(
            Engine="neural",
            VoiceId=VOICES[lang],
            Text=chunk,
            OutputFormat="mp3",
        )
        audio_parts.append(resp["AudioStream"].read())

    s3.put_object(
        Bucket=BUCKET,
        Key=f"audio/{slug}.{lang}.mp3",
        Body=b"".join(audio_parts),
        ContentType="audio/mpeg",
        CacheControl="max-age=31536000",
    )

    print(f"Generated audio/{slug}.{lang}.mp3")
