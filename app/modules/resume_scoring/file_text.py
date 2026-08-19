"""
Raw text extraction from resume attachments.

Only PDF and DOCX are supported (locked decision). Anything else raises
UnsupportedResumeFormat — Module 1's mail orchestration should catch this
and fall back to sending the resume-request mail.
"""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from docx import Document  # python-docx-ng package, same import namespace

from .config import SUPPORTED_RESUME_FORMATS


class UnsupportedResumeFormat(Exception):
    def __init__(self, extension: str):
        self.extension = extension
        super().__init__(f"Unsupported resume format: {extension!r}")


def extract_text(file_path: str | Path) -> str:
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in SUPPORTED_RESUME_FORMATS:
        raise UnsupportedResumeFormat(ext)

    if ext == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if ext == ".docx":
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)

    raise UnsupportedResumeFormat(ext)  # unreachable, keeps type-checkers happy