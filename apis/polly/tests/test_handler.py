import json
import io
from unittest.mock import patch, MagicMock

import handler
from handler import ArticleExtractor, inject_code_labels, to_ssml_chunks, PARA_BREAK


# ---------------------------------------------------------------------------
# ArticleExtractor
# ---------------------------------------------------------------------------

def test_extractor_captures_title():
    html = '<h1 class="single-title">Hello World</h1>'
    ex = ArticleExtractor()
    ex.feed(html)
    assert "Hello World" in ex.get_text()


def test_extractor_captures_content():
    html = '<div id="content"><p>Some article text.</p></div>'
    ex = ArticleExtractor()
    ex.feed(html)
    assert "Some article text." in ex.get_text()


def test_extractor_skips_code_blocks():
    html = '<div id="content"><p>Before.</p><pre><code>x = 1</code></pre><p>After.</p></div>'
    ex = ArticleExtractor()
    ex.feed(html)
    text = ex.get_text()
    assert "x = 1" not in text
    assert "Before." in text
    assert "After." in text


def test_extractor_skips_elements_with_skip_id():
    html = '<div id="chat-widget">Chat stuff</div><div id="content"><p>Real content.</p></div>'
    ex = ArticleExtractor()
    ex.feed(html)
    text = ex.get_text()
    assert "Chat stuff" not in text
    assert "Real content." in text


def test_extractor_skips_elements_with_skip_class():
    html = '<div id="content"><p>Good.</p><div class="post-tags">Tags here</div></div>'
    ex = ArticleExtractor()
    ex.feed(html)
    text = ex.get_text()
    assert "Tags here" not in text
    assert "Good." in text


def test_extractor_skips_script_and_style():
    html = '<div id="content"><script>alert(1)</script><p>Visible.</p></div>'
    ex = ArticleExtractor()
    ex.feed(html)
    text = ex.get_text()
    assert "alert" not in text
    assert "Visible." in text


def test_extractor_returns_empty_for_blank_html():
    ex = ArticleExtractor()
    ex.feed("<html><body></body></html>")
    assert ex.get_text() == ""


# ---------------------------------------------------------------------------
# inject_code_labels
# ---------------------------------------------------------------------------

def test_inject_code_labels_replaces_pre_block():
    html = "<p>Text</p><pre><code>print('hi')</code></pre><p>More</p>"
    result = inject_code_labels(html, "Code example.")
    assert "print" not in result
    assert "Code example." in result


def test_inject_code_labels_replaces_multiple_blocks():
    html = "<pre>first</pre><pre>second</pre>"
    result = inject_code_labels(html, "Code example.")
    assert result.count("Code example.") == 2


def test_inject_code_labels_is_case_insensitive():
    html = "<PRE>UPPER CASE</PRE>"
    result = inject_code_labels(html, "Code example.")
    assert "UPPER CASE" not in result
    assert "Code example." in result


# ---------------------------------------------------------------------------
# to_ssml_chunks
# ---------------------------------------------------------------------------

def test_ssml_short_text_produces_single_chunk():
    text = PARA_BREAK.join(["Hello world.", "How are you?"])
    chunks = to_ssml_chunks(text)
    assert len(chunks) == 1
    assert chunks[0].startswith("<speak>")
    assert chunks[0].endswith("</speak>")


def test_ssml_long_text_produces_multiple_chunks():
    segment = "word " * 100  # ~500 chars per segment
    text = PARA_BREAK.join([segment] * 10)  # ~5000 chars total
    chunks = to_ssml_chunks(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 2800 + len("<speak></speak>")


def test_ssml_escapes_html_special_chars():
    text = "5 > 3 & 2 < 4"
    chunks = to_ssml_chunks(text)
    assert "&amp;" in chunks[0]
    assert "&gt;" in chunks[0]
    assert "&lt;" in chunks[0]


def test_ssml_empty_text_returns_no_chunks():
    assert to_ssml_chunks("") == []


# ---------------------------------------------------------------------------
# lambda_handler
# ---------------------------------------------------------------------------

def make_event(key):
    return {
        "Records": [{
            "Sns": {
                "Message": json.dumps({
                    "Records": [{"s3": {"object": {"key": key}}}]
                })
            }
        }]
    }


def test_handler_skips_unsupported_language():
    event = make_event("content/posts/my-post/index.fr.md")
    with patch.object(handler, "boto3"):
        result = handler.lambda_handler(event, None)
    assert result is None


def test_handler_skips_when_html_not_found():
    mock_s3 = MagicMock()
    mock_s3.get_object.side_effect = Exception("NoSuchKey")

    with patch.object(handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_s3
        result = handler.lambda_handler(make_event("content/posts/my-post/index.en.md"), None)
    assert result is None


def test_handler_skips_when_content_hash_unchanged():
    html = '<h1 class="single-title">Post</h1><div id="content"><p>Hello.</p></div>'
    import hashlib
    from handler import ArticleExtractor as AE, inject_code_labels as icl, CODE_LABEL
    content = icl(html, CODE_LABEL["en"])
    ex = AE()
    ex.feed(content)
    text = ex.get_text()
    content_hash = hashlib.md5(text.encode()).hexdigest()

    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": io.BytesIO(html.encode())}
    mock_s3.head_object.return_value = {"Metadata": {"content-hash": content_hash}}

    with patch.object(handler, "boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_s3
        handler.lambda_handler(make_event("content/posts/my-post/index.en.md"), None)

    mock_s3.put_object.assert_not_called()


def test_handler_generates_and_uploads_audio():
    html = '<h1 class="single-title">Post</h1><div id="content"><p>Hello world.</p></div>'

    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": io.BytesIO(html.encode())}
    mock_s3.head_object.side_effect = Exception("NoSuchKey")

    mock_polly = MagicMock()
    mock_polly.synthesize_speech.return_value = {"AudioStream": io.BytesIO(b"mp3data")}

    def client_factory(service, **kwargs):
        return mock_s3 if service == "s3" else mock_polly

    with patch.object(handler, "boto3") as mock_boto3:
        mock_boto3.client.side_effect = client_factory
        handler.lambda_handler(make_event("content/posts/my-post/index.en.md"), None)

    mock_s3.put_object.assert_called_once()
    call_kwargs = mock_s3.put_object.call_args[1]
    assert call_kwargs["Key"] == "audio/my-post.en.mp3"
    assert call_kwargs["ContentType"] == "audio/mpeg"
