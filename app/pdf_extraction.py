"""
Extracts plain text from uploaded resume PDFs so it can be fed to the AI resume
analysis service. Only PDF is supported (as requested) - .doc/.docx resumes are
stored and downloadable as before, but are not text-extracted, since that needs a
different library (e.g. python-docx) and was out of scope for this change.
"""

from pathlib import Path

import pdfplumber

from app.config import settings


def resolve_upload_path(url: str | None) -> Path | None:
    """Maps a stored URL like '/uploads/resumes/xyz.pdf' back to its file on disk."""
    if not url or not url.startswith("/uploads/"):
        return None
    relative = url[len("/uploads/"):]
    path = Path(settings.UPLOAD_DIR) / relative
    return path if path.exists() else None


def extract_text_from_pdf(path: Path) -> str:
    """
    Extracts all text from a PDF file. Returns an empty string (rather than raising)
    if the file can't be parsed - e.g. a scanned/image-only PDF with no text layer -
    so callers can fall back gracefully instead of failing the whole request.
    """
    try:
        pages_text: list[str] = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                pages_text.append(page_text)
        return "\n".join(pages_text).strip()
    except Exception:
        return ""


def extract_resume_text(resume_url: str | None) -> str:
    """Convenience wrapper: stored resume URL -> extracted text (PDF only, '' otherwise)."""
    path = resolve_upload_path(resume_url)
    if path is None or path.suffix.lower() != ".pdf":
        return ""
    text = extract_text_from_pdf(path)
    return text[: settings.RESUME_TEXT_MAX_CHARS]
