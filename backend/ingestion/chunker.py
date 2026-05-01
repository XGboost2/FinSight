"""
Chunker — splits 10-K filings into chunks using SEC section structure.

Strategy:
  Primary   — detect Item boundaries (1, 1A, 1B, 2 ... 15) and chunk by section.
               Each section = one coherent topic. Much better retrieval than
               blind character splits.
  Fallback  — if <3 sections detected (malformed filing), fall back to
               character-based chunking with overlap.

Why sections beat character splits:
  A character chunk might contain half of "Risk Factors" + half of "Properties".
  A section chunk is always one topic. "What are the risks?" retrieves Item 1A,
  not a random 1000-char window that happens to mention the word risk.

Each chunk carries section metadata (item number, section name) which gets
stored in Qdrant payload — enabling filtered search later (Day 56).
"""

import hashlib
import logging
import re

logger = logging.getLogger(__name__)

# Standard 10-K section names per SEC Regulation S-K
SECTION_NAMES: dict[str, str] = {
    "1":   "Business",
    "1A":  "Risk Factors",
    "1B":  "Unresolved Staff Comments",
    "1C":  "Cybersecurity",
    "2":   "Properties",
    "3":   "Legal Proceedings",
    "4":   "Mine Safety Disclosures",
    "5":   "Market for Common Equity",
    "6":   "Selected Financial Data",
    "7":   "Management Discussion and Analysis",
    "7A":  "Quantitative Disclosures About Market Risk",
    "8":   "Financial Statements",
    "9":   "Changes in Disagreements with Accountants",
    "9A":  "Controls and Procedures",
    "9B":  "Other Information",
    "9C":  "Foreign Jurisdiction Disclosures",
    "10":  "Directors and Corporate Governance",
    "11":  "Executive Compensation",
    "12":  "Security Ownership",
    "13":  "Certain Relationships",
    "14":  "Principal Accountant Fees",
    "15":  "Exhibits",
    "16":  "Form 10-K Summary",
}

# Matches "Item 1A." or "ITEM 1A -" or "Item 7A:" at the start of a line.
# Groups: (1) item number e.g. "1A", (2) title text after the dot/dash
_SECTION_RE = re.compile(
    r"(?:^|\n)[ \t]*(?:ITEM|Item)[ \t]+(\d{1,2}[A-Ca-c]?)[ \t]*[.\-—:\t ]+([^\n]{0,120})",
    re.MULTILINE,
)

# Sections longer than this get split further by character (Item 8 can be 200k chars)
_MAX_SECTION_CHARS = 4000
_OVERLAP_CHARS = 200


def chunk_text(
    text: str,
    chunk_size: int = _MAX_SECTION_CHARS,
    chunk_overlap: int = _OVERLAP_CHARS,
    source_id: str = "",
) -> list[dict]:
    """Public API — same signature as before, now section-aware internally."""
    if not text:
        return []

    sections = _extract_sections(text)

    if len(sections) >= 3:
        logger.info(
            "Section-aware chunking: detected %d 10-K sections for %s",
            len(sections),
            source_id,
        )
        return _sections_to_chunks(sections, source_id, chunk_size, chunk_overlap)

    logger.warning(
        "Only %d sections detected for %s — falling back to character chunking",
        len(sections),
        source_id,
    )
    return _char_chunks(text, chunk_size, chunk_overlap, source_id)


# ── Section detection ──────────────────────────────────────────────────────────

def _extract_sections(text: str) -> list[dict]:
    """
    Find Item boundaries in the document.

    10-Ks have a table of contents (TOC) at the front where every Item appears
    once as a short reference line, then the actual content where each Item
    appears again with its full text. We group all occurrences of each item
    number and take the last one — that's always the content, not the TOC.
    """
    matches = list(_SECTION_RE.finditer(text))

    # Group matches by normalised item number (e.g. "1a" → "1A")
    by_item: dict[str, list] = {}
    for m in matches:
        key = m.group(1).upper()
        by_item.setdefault(key, []).append(m)

    # Take the last occurrence of each item (content, not TOC)
    content_matches = [occurrences[-1] for occurrences in by_item.values()]
    content_matches.sort(key=lambda m: m.start())

    sections = []
    for i, match in enumerate(content_matches):
        item_num = match.group(1).upper()
        title_from_doc = match.group(2).strip()

        # Text runs from after this header to the start of the next one
        start = match.end()
        end = content_matches[i + 1].start() if i + 1 < len(content_matches) else len(text)
        body = text[start:end].strip()

        if not body:
            continue

        canonical_name = SECTION_NAMES.get(item_num, title_from_doc[:60])

        sections.append({
            "item": item_num,
            "section": canonical_name,
            # Prepend header so every chunk knows its own context
            "text": f"Item {item_num} — {canonical_name}\n\n{body}",
        })

    return sections


# ── Chunk building ─────────────────────────────────────────────────────────────

def _sections_to_chunks(
    sections: list[dict],
    source_id: str,
    max_chars: int,
    overlap: int,
) -> list[dict]:
    """Turn detected sections into final chunks, splitting large ones further."""
    chunks: list[dict] = []

    for section in sections:
        text = section["text"]

        if len(text) <= max_chars:
            chunks.append(_make_chunk(
                text=text,
                index=len(chunks),
                source_id=source_id,
                item=section["item"],
                section=section["section"],
            ))
        else:
            # Large section (e.g. Item 8 Financial Statements) — split by chars
            # but keep section metadata on every sub-chunk
            sub_chunks = _char_chunks(text, max_chars, overlap, source_id)
            for sub in sub_chunks:
                sub["item"] = section["item"]
                sub["section"] = section["section"]
                sub["chunk_index"] = len(chunks)
                chunks.append(sub)

    logger.info(
        "Chunked into %d chunks across %d sections for %s",
        len(chunks),
        len(sections),
        source_id,
    )
    return chunks


def _make_chunk(
    text: str,
    index: int,
    source_id: str,
    item: str = "",
    section: str = "",
) -> dict:
    chunk_id = hashlib.sha256(f"{source_id}_{index}".encode()).hexdigest()[:10]
    return {
        "id": chunk_id,
        "text": text,
        "chunk_index": index,
        "item": item,
        "section": section,
        "char_start": 0,
        "char_end": len(text),
        "source_id": source_id,
    }


def _char_chunks(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    source_id: str,
) -> list[dict]:
    """Original paragraph-aware character chunker — used as fallback."""
    paragraphs = text.split("\n\n")
    chunks: list[dict] = []
    current = ""
    current_start = 0
    char_pos = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            char_pos += 2
            continue

        if current and len(current) + len(para) + 2 > chunk_size:
            chunks.append(_make_chunk(current.strip(), len(chunks), source_id))

            if chunk_overlap > 0 and len(current) > chunk_overlap:
                overlap_text = current[-chunk_overlap:]
                current_start = current_start + len(current) - chunk_overlap
                current = overlap_text + "\n\n" + para
            else:
                current_start = char_pos
                current = para
        else:
            current = (current + "\n\n" + para) if current else para
            if not current:
                current_start = char_pos

        char_pos += len(para) + 2

    if current.strip():
        chunks.append(_make_chunk(current.strip(), len(chunks), source_id))

    return chunks
