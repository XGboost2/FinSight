from ingestion.pageindex import enrich_chunks_with_pageindex, extract_pageindex_sections


def test_extract_pageindex_sections_from_markdown_headings():
    text = "# Overview\nRevenue summary.\n\n## Risks\nSupply risk."

    sections = extract_pageindex_sections(text)

    assert [section.title for section in sections] == ["Overview", "Risks"]
    assert [section.level for section in sections] == [1, 2]


def test_enrich_chunks_with_pageindex_metadata():
    text = "# Overview\nRevenue summary.\n\n## Risks\nSupply risk."
    chunks = [
        {"chunk_index": 0, "text": "# Overview\nRevenue summary."},
        {"chunk_index": 1, "text": "## Risks\nSupply risk."},
    ]

    enriched = enrich_chunks_with_pageindex(text, chunks)

    assert enriched[0]["item"] == "pageindex:1"
    assert enriched[0]["section"] == "Overview"
    assert enriched[1]["item"] == "pageindex:2"
    assert enriched[1]["section"] == "Risks"


def test_enrich_chunks_with_pageindex_uses_chunk_position_for_body_text():
    text = "# Overview\nRevenue summary.\n\n## Risks\nSupply risk.\nCustomer concentration."
    chunks = [
        {"chunk_index": 0, "text": "Revenue summary.", "item": "", "section": ""},
        {"chunk_index": 1, "text": "Supply risk.\nCustomer concentration.", "item": "", "section": ""},
    ]

    enriched = enrich_chunks_with_pageindex(text, chunks)

    assert enriched[0]["item"] == "pageindex:1"
    assert enriched[0]["section"] == "Overview"
    assert enriched[1]["item"] == "pageindex:2"
    assert enriched[1]["section"] == "Risks"
