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

PARA_BREAK = "\x00"


class ArticleExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_content = False
        self.content_depth = 0
        self.skip_tags = {"pre", "script", "style"}
        self.skip_depth = 0
        self.in_pre = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if not self.in_content:
            if attrs_dict.get("id") == "content":
                self.in_content = True
                self.content_depth = 1
        else:
            if tag == "div":
                self.content_depth += 1
            if tag == "pre":
                self.in_pre = True
            elif tag in self.skip_tags:
                self.skip_depth += 1

    def handle_endtag(self, tag):
        if not self.in_content:
            return
        if tag in ("p", "h1", "h2", "h3", "h4", "li", "hr"):
            if not self.in_pre and self.skip_depth == 0:
                self.parts.append(PARA_BREAK)
        elif tag == "pre":
            self.in_pre = False
            self.parts.append(PARA_BREAK)
        elif tag in self.skip_tags:
            self.skip_depth -= 1
        elif tag == "div":
            self.content_depth -= 1
            if self.content_depth == 0:
                self.in_content = False

    def handle_data(self, data):
        if self.in_content and not self.in_pre and self.skip_depth == 0:
            self.parts.append(data)

    def get_text(self):
        text = "".join(self.parts)
        segments = text.split(PARA_BREAK)
        segments = [re.sub(r"\s+", " ", s).strip() for s in segments]
        segments = [s for s in segments if s]
        return PARA_BREAK.join(segments)


def inject_code_labels(html_content, label):
    return re.sub(
        r"<pre[\s\S]*?</pre>",
        f" {label} ",
        html_content,
        flags=re.IGNORECASE,
    )


SSML_BREAK = '<break time="600ms"/>'
MAX_SSML_CHARS = 2800


def to_ssml_chunks(text):
    segments = text.split(PARA_BREAK)
    chunks = []
    current = ""

    for segment in segments:
        addition = (SSML_BREAK if current else "") + segment
        if len(current) + len(addition) > MAX_SSML_CHARS:
            if current:
                chunks.append(f"<speak>{current}</speak>")
            current = segment
        else:
            current += addition

    if current:
        chunks.append(f"<speak>{current}</speak>")

    return chunks


def lambda_handler(event, _context):
    s3 = boto3.client("s3", region_name="eu-central-1")
    polly = boto3.client("polly", region_name="eu-central-1")

    record = event["Records"][0]
    key = record["s3"]["object"]["key"]
    parts = key.split("/")
    slug = parts[2]
    lang = parts[3].split(".")[1]

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

    audio_parts = []
    for chunk in to_ssml_chunks(text):
        resp = polly.synthesize_speech(
            Engine="neural",
            VoiceId=VOICES[lang],
            Text=chunk,
            TextType="ssml",
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
