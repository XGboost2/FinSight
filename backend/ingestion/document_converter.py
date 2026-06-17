"""Document conversion utilities for user-uploaded files.

MarkItDown normalizes PDFs, Office docs, HTML, images, and structured files into
Markdown/text that can flow through FinSight's existing chunking and RAG path.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import re
import tempfile


class DocumentConversionUnavailable(RuntimeError):
    """Raised when the optional MarkItDown dependency is not installed."""


class DocumentConversionError(RuntimeError):
    """Raised when MarkItDown cannot extract useful text from a file."""


@dataclass(frozen=True)
class ConvertedDocument:
    filename: str
    text: str
    chars: int


def clean_converted_text(text: str) -> str:
    """Remove residual markup/noise from converted upload text before indexing."""
    text = unescape(text or "")
    text = re.sub(r"(?is)<(script|style|noscript|svg|meta|head)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(?:p|div|section|article|header|footer|tr|li|h[1-6])>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\b(?:class|style|id|href|src|alt|title)=\"[^\"]*\"", " ", text)
    text = re.sub(r"\b(?:class|style|id|href|src|alt|title)='[^']*'", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def convert_document_bytes(filename: str, content: bytes) -> ConvertedDocument:
    """Convert uploaded file bytes to Markdown/text via MarkItDown.

    The API accepts bytes, not user-provided filesystem paths, so MarkItDown only
    reads a server-created temp file with the current process privileges.
    """
    if not content:
        raise DocumentConversionError("Uploaded file is empty")

    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise DocumentConversionUnavailable(
            "MarkItDown is not installed. Install backend dependency: markitdown[all]"
        ) from exc

    suffix = Path(filename).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(content)
        tmp.flush()

        try:
            result = MarkItDown(enable_plugins=False).convert(tmp.name)
        except Exception as exc:
            raise DocumentConversionError(f"MarkItDown conversion failed: {exc}") from exc

    text = clean_converted_text(
        getattr(result, "text_content", None) or getattr(result, "markdown", None) or ""
    )
    if not text:
        raise DocumentConversionError("MarkItDown produced no text")

    return ConvertedDocument(filename=filename, text=text, chars=len(text))
