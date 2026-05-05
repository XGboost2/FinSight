"""
Section extractor — parses Item 1, 1A, 7 from cleaned 10-K filing text.

10-K filings follow a standard SEC structure. We locate section headers
using regex and slice the text between them. We use the LAST match of
each header to skip the table of contents (which lists all sections near
the top of the document before the actual content begins).
"""

import logging
import re

logger = logging.getLogger(__name__)

# Regex patterns for each section header — matched case-insensitively
_PATTERNS: dict[str, str] = {
    "item_1":  r"item\s+1[\.\s]+business\b",
    "item_1a": r"item\s+1a[\.\s]+risk\s+factors",
    "item_7":  r"item\s+7[\.\s]+management.{0,20}discussion",
    "item_7a": r"item\s+7a[\.\s]+quantitative",
    "item_8":  r"item\s+8[\.\s]+financial\s+statements",
}

# Document order — used to determine where each section ends
_ORDER = ["item_1", "item_1a", "item_7", "item_7a", "item_8"]

# Cap each section at 40k chars to keep LLM context manageable
_MAX_CHARS = 40_000


def extract_sections(text: str) -> dict[str, str]:
    """Extract key 10-K sections from cleaned filing text.

    Returns {section_key: section_text} for sections found.
    Uses last match per pattern to skip table of contents.
    """
    text_lower = text.lower()
    positions: dict[str, int] = {}

    for key in _ORDER:
        matches = list(re.finditer(_PATTERNS[key], text_lower))
        if matches:
            positions[key] = matches[-1].start()

    if not positions:
        logger.warning("No standard 10-K sections found in filing text")
        return {}

    ordered = sorted(positions.items(), key=lambda x: x[1])
    result: dict[str, str] = {}

    for i, (key, start) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else start + _MAX_CHARS
        result[key] = text[start:end].strip()[:_MAX_CHARS]

    logger.info("Extracted sections: %s", {k: f"{len(v):,} chars" for k, v in result.items()})
    return result


def split_paragraphs(text: str, min_len: int = 80) -> list[str]:
    """Split section text into meaningful paragraphs, filtering noise."""
    paragraphs = re.split(r"\n{2,}", text)
    return [p.strip() for p in paragraphs if len(p.strip()) >= min_len]
