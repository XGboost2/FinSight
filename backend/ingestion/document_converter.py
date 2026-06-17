"""Document conversion utilities for user-uploaded files.

MarkItDown normalizes PDFs, Office docs, HTML, images, and structured files into
Markdown/text that can flow through FinSight's existing chunking and RAG path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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

    text = (getattr(result, "text_content", None) or getattr(result, "markdown", None) or "").strip()
    if not text:
        raise DocumentConversionError("MarkItDown produced no text")

    return ConvertedDocument(filename=filename, text=text, chars=len(text))
