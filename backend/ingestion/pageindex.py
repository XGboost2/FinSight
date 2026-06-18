"""PageIndex-style structure extraction for uploaded documents.

This is not a separate retrieval database. MarkItDown converts arbitrary files
to Markdown/text; this module recovers lightweight document structure from that
text so Neo4j can store an inspectable Document -> Section -> Chunk graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class PageIndexSection:
    section_id: str
    title: str
    level: int
    start: int
    end: int


def extract_pageindex_sections(text: str) -> list[PageIndexSection]:
    """Extract Markdown heading ranges from converted upload text."""
    matches = list(_HEADING_RE.finditer(text or ""))
    sections: list[PageIndexSection] = []
    for index, match in enumerate(matches):
        title = re.sub(r"\s+", " ", match.group(2)).strip(" #:-")
        if not title:
            continue
        sections.append(PageIndexSection(
            section_id=f"pageindex:{index + 1}",
            title=title[:120],
            level=len(match.group(1)),
            start=match.start(),
            end=matches[index + 1].start() if index + 1 < len(matches) else len(text),
        ))
    return sections


def enrich_chunks_with_pageindex(text: str, chunks: list[dict]) -> list[dict]:
    """Attach PageIndex-style structure metadata to uploaded chunks.

    The SEC chunker already handles 10-K/10-Q/8-K Item sections. For custom
    uploads, this function fills in missing section metadata from Markdown
    headings produced by MarkItDown.
    """
    sections = extract_pageindex_sections(text)
    enriched: list[dict] = []
    offsets = _locate_chunk_offsets(text or "", chunks)

    for index, chunk in enumerate(chunks):
        updated = dict(chunk)
        section = _section_for_chunk(updated, sections, offsets[index])
        if section:
            if not updated.get("item"):
                updated["item"] = section.section_id
            if not updated.get("section"):
                updated["section"] = section.title
            updated["pageindex_section_id"] = section.section_id
            updated["pageindex_section"] = section.title
            updated["pageindex_level"] = section.level
        else:
            if not updated.get("item"):
                updated["item"] = "DOCUMENT"
            if not updated.get("section"):
                updated["section"] = "Document"
            updated.setdefault("pageindex_section_id", updated["item"])
            updated.setdefault("pageindex_section", updated["section"])
            updated.setdefault("pageindex_level", 0)
        enriched.append(updated)

    return enriched


def _locate_chunk_offsets(text: str, chunks: list[dict]) -> list[int]:
    offsets: list[int] = []
    cursor = 0
    for chunk in chunks:
        chunk_text = chunk.get("text", "")
        found = text.find(chunk_text, cursor)
        if found < 0:
            found = text.find(chunk_text)
        offsets.append(found if found >= 0 else int(chunk.get("char_start") or 0))
        if found >= 0:
            cursor = found + max(1, len(chunk_text))
    return offsets


def _section_for_chunk(
    chunk: dict,
    sections: list[PageIndexSection],
    offset: int,
) -> PageIndexSection | None:
    if not sections:
        return None

    text = chunk.get("text", "")
    for section in sections:
        if section.title and section.title in text:
            return section

    start = offset if offset >= 0 else int(chunk.get("char_start") or 0)
    candidates = [section for section in sections if section.start <= start < section.end]
    if candidates:
        return candidates[-1]

    return None
