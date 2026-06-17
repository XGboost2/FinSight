from ingestion.document_converter import clean_converted_text


def test_clean_converted_text_removes_html_noise():
    raw = """
    <html><head><style>.x{color:red}</style><script>alert(1)</script></head>
    <body><h1>Risk Factors</h1><p>Competition &amp; pricing pressure.</p>
    <div class="note"><a href="https://example.com">SanDisk</a></div></body></html>
    """

    cleaned = clean_converted_text(raw)

    assert "<" not in cleaned
    assert ">" not in cleaned
    assert "alert" not in cleaned
    assert "Risk Factors" in cleaned
    assert "Competition & pricing pressure." in cleaned
    assert "SanDisk" in cleaned
