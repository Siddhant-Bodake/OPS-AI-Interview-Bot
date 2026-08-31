"""
Async URL-based resume download with SSRF protection.

Supports:
- S3 presigned URLs (any *.amazonaws.com host)
- Google Drive sharing links (converted to direct download)
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from . import config


class ResumeURLError(Exception):
    """Base exception for URL-based resume download failures."""


class DomainNotAllowedError(ResumeURLError):
    """Raised when the URL domain is not in the allowlist."""


class GoogleDriveAccessError(ResumeURLError):
    """Raised when Google Drive returns an access error or HTML page."""


class ResumeDownloadTimeoutError(ResumeURLError):
    """Raised when the download exceeds the configured timeout."""


class ResumeTooLargeError(ResumeURLError):
    """Raised when the file exceeds the configured max size."""


def _is_gdrive_url(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower() in config.GOOGLE_DRIVE_DOMAINS


def _domain_allowed(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if not hostname:
        return False

    if _is_gdrive_url(url):
        return True

    allowed = [d.strip().lower() for d in settings.ALLOWED_RESUME_DOMAINS.split(",") if d.strip()]
    return any(hostname == d or hostname.endswith("." + d) for d in allowed)


def _parse_gdrive_file_id(url: str) -> str | None:
    for pattern in (config.GOOGLE_DRIVE_URL_PATTERN, config.GOOGLE_DRIVE_OPEN_PATTERN, config.GOOGLE_DRIVE_UC_PATTERN):
        m = pattern.search(url)
        if m:
            return m.group(1)
    return None


def _is_html_content(content_type: str) -> bool:
    return "text/html" in content_type.lower()


def _extract_gdrive_download_token(html: str) -> str | None:
    """Extract the download token/confirm parameter from Google Drive HTML page."""
    match = re.search(r'href="(/uc\?export=download[^"]*confirm=[^"]*)"', html)
    if match:
        return match.group(1)
    match = re.search(r'id="uc-download-link"[^>]*href="([^"]+)"', html)
    if match:
        return match.group(1)
    return None


def _gdrive_download_urls(file_id: str) -> list[str]:
    """Return multiple Google Drive download URLs to try, in order of preference."""
    return [
        f"https://drive.google.com/uc?export=download&id={file_id}",
        f"https://drive.usercontent.google.com/download?id={file_id}&export=download",
        f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t",
        f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t",
    ]


def _infer_extension(content_type: str | None, url: str) -> str:
    ct_map = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/msword": ".doc",
    }
    if content_type:
        ct_base = content_type.split(";")[0].strip().lower()
        if ct_base in ct_map:
            return ct_map[ct_base]

    path = Path(urlparse(url).path)
    ext = path.suffix.lower()
    if ext in {".pdf", ".docx", ".doc"}:
        return ext

    return ".pdf"


async def _fetch_gdrive(client: httpx.AsyncClient, file_id: str, url: str) -> httpx.Response | None:
    """Try to download from a single Google Drive URL. Returns Response if successful file download, None if HTML."""
    try:
        response = await client.get(url, headers={"User-Agent": "ResumeScoringBot/1.0"})
    except (httpx.TimeoutException, httpx.RequestError):
        return None

    if response.status_code != 200:
        return None

    content_type = response.headers.get("content-type", "")
    if _is_html_content(content_type):
        return None

    return response


async def download_resume_from_url(url: str) -> tuple[str, str]:
    if not _domain_allowed(url):
        raise DomainNotAllowedError(
            f"URL domain not in allowlist: {urlparse(url).hostname!r}. "
            f"Allowed domains: {settings.ALLOWED_RESUME_DOMAINS}"
        )

    is_gdrive = _is_gdrive_url(url)

    if not is_gdrive:
        return await _download_direct(url)

    file_id = _parse_gdrive_file_id(url)
    if not file_id:
        raise ResumeURLError(f"Cannot extract file ID from Google Drive URL: {url}")

    return await _download_gdrive(file_id)


async def _download_direct(url: str) -> tuple[str, str]:
    """Download from a non-Google-Drive URL (e.g., S3 presigned URL)."""
    timeout = httpx.Timeout(settings.RESUME_DOWNLOAD_TIMEOUT)

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, max_redirects=5) as client:
        try:
            response = await client.get(url, headers={"User-Agent": "ResumeScoringBot/1.0"})
        except httpx.TimeoutException:
            raise ResumeDownloadTimeoutError(f"Download timed out after {settings.RESUME_DOWNLOAD_TIMEOUT}s: {url}")
        except httpx.RequestError as e:
            raise ResumeURLError(f"Failed to download resume from URL: {e}")

        if response.status_code == 403:
            raise ResumeURLError(f"HTTP 403 Forbidden when downloading from: {url}")
        if response.status_code == 404:
            raise ResumeURLError(f"HTTP 404 Not Found: {url}")
        if response.status_code >= 400:
            raise ResumeURLError(f"HTTP {response.status_code} error downloading from: {url}")

        content_type = response.headers.get("content-type", "")
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > settings.RESUME_MAX_URL_FILE_SIZE:
            raise ResumeTooLargeError(
                f"File too large: {int(content_length)} bytes (max: {settings.RESUME_MAX_URL_FILE_SIZE} bytes)"
            )

        suffix = _infer_extension(content_type, url)
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        total_bytes = 0
        tmp_path = tmp.name
        try:
            async for chunk in response.aiter_bytes(chunk_size=65536):
                total_bytes += len(chunk)
                if total_bytes > settings.RESUME_MAX_URL_FILE_SIZE:
                    raise ResumeTooLargeError(
                        f"File too large: exceeded {settings.RESUME_MAX_URL_FILE_SIZE} bytes during download"
                    )
                tmp.write(chunk)
        except Exception:
            tmp.close()
            os.unlink(tmp_path)
            raise
        finally:
            tmp.close()

    return tmp_path, suffix


async def _download_gdrive(file_id: str) -> tuple[str, str]:
    """Download from Google Drive, trying multiple URL patterns."""
    urls = _gdrive_download_urls(file_id)
    timeout = httpx.Timeout(settings.RESUME_DOWNLOAD_TIMEOUT)

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, max_redirects=10) as client:
        last_error = None

        for download_url in urls:
            try:
                response = await client.get(download_url, headers={"User-Agent": "ResumeScoringBot/1.0"})
            except httpx.TimeoutException:
                raise ResumeDownloadTimeoutError(
                    f"Google Drive download timed out after {settings.RESUME_DOWNLOAD_TIMEOUT}s"
                )
            except httpx.RequestError:
                continue

            if response.status_code == 403:
                raise GoogleDriveAccessError(
                    "Google Drive returned 403 Forbidden. "
                    "The file may not be shared publicly. "
                    "Please set sharing to 'Anyone with the link'."
                )

            if response.status_code == 404:
                raise GoogleDriveAccessError(
                    "Google Drive returned 404 Not Found. "
                    "The file may have been deleted or the link is invalid."
                )

            if response.status_code >= 400:
                last_error = f"HTTP {response.status_code}"
                continue

            content_type = response.headers.get("content-type", "")

            if not _is_html_content(content_type):
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > settings.RESUME_MAX_URL_FILE_SIZE:
                    raise ResumeTooLargeError(
                        f"File too large: {int(content_length)} bytes (max: {settings.RESUME_MAX_URL_FILE_SIZE} bytes)"
                    )

                suffix = _infer_extension(content_type, download_url)
                tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
                total_bytes = 0
                tmp_path = tmp.name
                try:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        total_bytes += len(chunk)
                        if total_bytes > settings.RESUME_MAX_URL_FILE_SIZE:
                            raise ResumeTooLargeError(
                                f"File too large: exceeded {settings.RESUME_MAX_URL_FILE_SIZE} bytes during download"
                            )
                        tmp.write(chunk)
                except Exception:
                    tmp.close()
                    os.unlink(tmp_path)
                    raise
                finally:
                    tmp.close()

                return tmp_path, suffix

        raise GoogleDriveAccessError(
            "Google Drive returned an HTML page instead of the file. "
            "Please ensure the file is shared as 'Anyone with the link' and try again, "
            "or download the file manually and upload it directly."
        )
