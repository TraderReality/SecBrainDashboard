"""Sicherer DokuLader-Kern für das SECBrain-Watcher-Webinterface."""

import base64
from contextlib import contextmanager
import binascii
import hashlib
import ipaddress
import os
import re
import socket
import stat
import tempfile
import time
import urllib.parse
import zipfile
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup
from markdownify import markdownify

from scanner.write_guard import PlannedChange, RuleBlocked, VaultWriteGuard
from scanner.inventory import _FILE_FLAGS
from scanner.safe_files import (_parent_directory, _atomic_new_file, _atomic_replace_file,
                                _remove_file)


MAX_URLS = 20
MAX_HTML_BYTES = 5 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_PDF_BYTES = 64 * 1024 * 1024
MAX_PDF_PAGES = 10_000
PDF_PAGES_PER_CHUNK = 50
MAX_ZIP_FILES = 5000
MAX_ZIP_FILE_BYTES = 8 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 256 * 1024 * 1024
MAX_ZIP_RATIO = 200
PACKAGE_MD_THRESHOLD = 100
USER_AGENT = "Mozilla/5.0 (compatible; SECBrain-DokuLader/2.5)"


def slugify_id(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-+", "-", text) or "dokumentation"


def _frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    try:
        return yaml.safe_load(text.split("---\n", 2)[1]) or {}
    except yaml.YAMLError:
        return {}


def existing_vault_metadata(vault: Path) -> tuple[set[str], set[str], set[str]]:
    ids: set[str] = set()
    sources: set[str] = set()
    hashes: set[str] = set()
    for path in vault.rglob("*.md") if vault.exists() else ():
        if "_index" in path.parts:
            continue
        try:
            with _parent_directory(path) as directory:
                descriptor = os.open(path.name, _FILE_FLAGS, dir_fd=directory)
                with os.fdopen(descriptor, "rb") as handle:
                    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                        continue
                    text = handle.read().decode("utf-8", errors="ignore")
        except (OSError, RuleBlocked):
            continue
        metadata = _frontmatter(text)
        if metadata.get("id"):
            ids.add(str(metadata["id"]).strip())
        if metadata.get("quelle"):
            sources.add(str(metadata["quelle"]).strip())
        if metadata.get("paket_sha256"):
            hashes.add(str(metadata["paket_sha256"]).strip())
    return ids, sources, hashes


def _unique_id(base: str, existing: set[str]) -> str:
    candidate = base
    suffix = 1
    while candidate in existing:
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def _rollback_installed(installed):
    conflicts = []
    for target, expected in reversed(installed):
        try:
            _remove_file(target, expected)
        except (OSError, RuleBlocked):
            conflicts.append(target.name)
    if conflicts:
        raise RuleBlocked("Rückweg bleibt offen; fremde Dateien erhalten: " + ", ".join(conflicts))


@contextmanager
def _temporary_input(vault: Path, content: bytes, suffix: str):
    directory = Path(tempfile.gettempdir()).resolve()
    if directory.is_relative_to(vault.resolve()):
        raise RuleBlocked("Temporäre Verarbeitung muss außerhalb der Vault liegen.")
    with tempfile.NamedTemporaryFile(suffix=suffix, dir=directory) as temporary:
        temporary.write(content)
        temporary.flush()
        yield Path(temporary.name)


def _validated_web_url(raw_url: str) -> str:
    url = raw_url.strip()
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"Ungültige Web-URL: {raw_url}")
    try:
        default_port = 443 if parsed.scheme == "https" else 80
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or default_port)}
    except socket.gaierror as exc:
        raise ValueError(f"Hostname nicht erreichbar: {parsed.hostname}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError(f"Lokale oder private Zieladresse ist nicht erlaubt: {parsed.hostname}")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _fetch_html_once(raw_url: str) -> tuple[str, str]:
    url = _validated_web_url(raw_url)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    response = None
    for _redirect in range(6):
        response = requests.get(url, headers=headers, timeout=(5, 20), stream=True, allow_redirects=False)
        if response.status_code not in {301, 302, 303, 307, 308}:
            break
        location = response.headers.get("Location")
        response.close()
        if not location:
            raise ValueError("HTTP-Weiterleitung ohne Zieladresse.")
        url = _validated_web_url(urllib.parse.urljoin(url, location))
    else:
        raise ValueError("Zu viele HTTP-Weiterleitungen.")

    with response:
        response.raise_for_status()
        final_url = url
        content_type = response.headers.get("Content-Type", "").lower()
        declared_size = int(response.headers.get("Content-Length") or 0)
        if declared_size > MAX_HTML_BYTES:
            raise ValueError("Die Webseite ist größer als 5 MiB.")
        chunks = []
        total = 0
        for chunk in response.iter_content(64 * 1024):
            total += len(chunk)
            if total > MAX_HTML_BYTES:
                raise ValueError("Die Webseite ist größer als 5 MiB.")
            chunks.append(chunk)
        raw = b"".join(chunks)
        encoding = response.encoding or "utf-8"
        html = raw.decode(encoding, errors="replace")
        if "html" not in content_type and not html.lstrip().lower().startswith(("<!doctype", "<html")):
            raise ValueError("Die URL liefert keinen HTML-Inhalt.")
        return final_url, html


def _html_to_markdown(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else "Dokumentation"
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    candidates = soup.select("main, article, #content, .content, #main, .document, .page")
    content = max(candidates, key=lambda item: len(item.get_text(strip=True))) if candidates else (soup.body or soup)
    if len(content.get_text(strip=True)) < 200:
        raise ValueError("Auf der Seite wurde zu wenig Dokumentationsinhalt gefunden.")
    body = markdownify(str(content), heading_style="ATX", bullets="-")
    return title.strip(), re.sub(r"\n{3,}", "\n\n", body).strip()


def import_urls(vault: Path, urls: list[str], guard: VaultWriteGuard) -> dict:
    cleaned = list(dict.fromkeys(url.strip() for url in urls if url.strip()))
    if not cleaned:
        raise ValueError("Mindestens eine URL ist erforderlich.")
    if len(cleaned) > MAX_URLS:
        raise ValueError(f"Maximal {MAX_URLS} URLs pro Import.")
    ids, sources, _ = existing_vault_metadata(vault)
    inbox = vault / "01 Inbox"
    today = time.strftime("%Y-%m-%d")
    imported = []
    skipped = []
    errors = []
    prepared = []
    for raw_url in cleaned:
        try:
            normalized_url = urllib.parse.urlunsplit((*urllib.parse.urlsplit(raw_url)[:4], ""))
            if normalized_url in sources:
                skipped.append({"url": normalized_url, "reason": "bereits in der Vault"})
                continue
            final_url, html = _fetch_html_once(raw_url)
            if final_url in sources:
                skipped.append({"url": final_url, "reason": "bereits in der Vault"})
                continue
            title, body = _html_to_markdown(html)
            note_id = _unique_id(slugify_id(title), ids)
            metadata = yaml.safe_dump({
                "id": note_id,
                "typ": "inboxed",
                "titel": title,
                "status": "entwurf",
                "erstellt": today,
                "geaendert": today,
                "quelle": final_url,
                "tags": ["eingang", "doku", "web-import"],
            }, allow_unicode=True, sort_keys=False)
            note = (
                f"---\n{metadata}---\n\n# {title}\n\n## Herkunft\n\n"
                f"Heruntergeladen von {final_url} am {today} mit DokuLader.\n\n## Inhalt\n\n{body}\n"
            )
            target = inbox / f"{note_id}.md"
            if target.exists():
                raise FileExistsError(f"{target.name} existiert bereits.")
            prepared.append((PlannedChange(target.relative_to(vault).as_posix(), "create", None,
                                           note.encode("utf-8")), final_url, raw_url))
            ids.add(note_id)
            sources.add(final_url)
        except Exception as exc:
            errors.append({"url": raw_url, "reason": str(exc)})
    if prepared:
        # Fetch and convert the complete batch before the first Vault mutation.
        with guard.authorize([item[0] for item in prepared], approval=None):
            installed = []
            try:
                for change, final_url, raw_url in prepared:
                    target = vault / change.relative_path
                    installed.append((target, _atomic_new_file(target, change.after_bytes)))
            except Exception as exc:
                # The authorized batch is one mutation: stop installing and
                # undo its completed writes before releasing the app lock.
                _rollback_installed(installed)
                if isinstance(exc, RuleBlocked):
                    raise
                errors.extend({"url": raw_url, "reason": f"Import-Batch zurückgerollt: {exc}"}
                              for _, _, raw_url in prepared)
            else:
                imported.extend({"filename": (vault / change.relative_path).name, "url": final_url}
                                for change, final_url, _ in prepared)
    return {"status": "completed", "imported": imported, "skipped": skipped, "errors": errors}


def _decode_archive(content_base64: str) -> bytes:
    if len(content_base64 or "") > (MAX_ARCHIVE_BYTES * 4 // 3) + 8:
        raise ValueError("Das ZIP-Archiv ist größer als 64 MiB.")
    try:
        content = base64.b64decode(content_base64 or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Die ZIP-Daten sind ungültig.") from exc
    if not content or len(content) > MAX_ARCHIVE_BYTES:
        raise ValueError("Das ZIP-Archiv muss zwischen 1 Byte und 64 MiB groß sein.")
    return content


def _decode_pdf(content_base64: str) -> bytes:
    if len(content_base64 or "") > (MAX_PDF_BYTES * 4 // 3) + 8:
        raise ValueError("Das PDF ist größer als 64 MiB.")
    try:
        content = base64.b64decode(content_base64 or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Die PDF-Daten sind ungültig.") from exc
    if not content or len(content) > MAX_PDF_BYTES:
        raise ValueError("Das PDF muss zwischen 1 Byte und 64 MiB groß sein.")
    if not content.lstrip().startswith(b"%PDF-"):
        raise ValueError("Die Datei ist kein gültiges PDF.")
    return content


def _convert_pdf_to_pages(path: Path) -> list[dict]:
    try:
        import pymupdf
        import pymupdf4llm
    except ImportError as exc:
        raise RuntimeError("PDF-Unterstützung ist nicht installiert (pymupdf4llm).") from exc
    try:
        with pymupdf.open(path) as document:
            page_count = document.page_count
        if page_count < 1 or page_count > MAX_PDF_PAGES:
            raise ValueError(f"PDFs müssen 1 bis {MAX_PDF_PAGES} Seiten enthalten.")
        pages = pymupdf4llm.to_markdown(
            str(path), page_chunks=True, show_progress=False, write_images=False, ignore_images=True
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"PDF konnte nicht gelesen werden: {exc}") from exc
    if not isinstance(pages, list) or not pages:
        raise ValueError("Im PDF wurde kein auslesbarer Inhalt gefunden.")
    return pages


def import_pdf(vault: Path, filename: str, content_base64: str, guard: VaultWriteGuard) -> dict:
    name = Path(filename or "").name
    if name != filename or not name.lower().endswith(".pdf"):
        raise ValueError("Ein PDF-Handbuch muss eine einfache .pdf-Datei sein.")
    content = _decode_pdf(content_base64)
    digest = hashlib.sha256(content).hexdigest()
    ids, _, hashes = existing_vault_metadata(vault)
    if digest in hashes:
        raise FileExistsError("Dieses PDF-Handbuch ist bereits in der Vault.")

    with _temporary_input(vault, content, ".pdf") as temporary:
        pages = _convert_pdf_to_pages(temporary)
    if len(pages) > MAX_PDF_PAGES:
        raise ValueError(f"PDFs dürfen höchstens {MAX_PDF_PAGES} Seiten enthalten.")

    archive_root = vault / "07 Anhänge" / "Dokumentationspakete"
    package_name = f"{slugify_id(Path(name).stem)}-{digest[:12]}"
    package_target = archive_root / package_name
    if package_target.exists():
        raise FileExistsError("Dieses PDF-Paket ist bereits im Dokumentationsarchiv vorhanden.")
    relative_package = package_target.relative_to(vault).as_posix()
    prepared = [PlannedChange(f"{relative_package}/{name}", "create", None, content)]
    chunks = []
    for start in range(0, len(pages), PDF_PAGES_PER_CHUNK):
        group = pages[start:start + PDF_PAGES_PER_CHUNK]
        first_page = start + 1
        last_page = start + len(group)
        chunk_name = f"teil-{(start // PDF_PAGES_PER_CHUNK) + 1:04d}-seiten-{first_page:04d}-{last_page:04d}.md"
        body_parts = []
        for index, page in enumerate(group, start=first_page):
            text = str(page.get("text", "")).strip()
            body_parts.append(f"<!-- PDF-Seite {index} -->\n\n{text}")
        chunk = f"# {Path(name).stem} — Seiten {first_page}–{last_page}\n\n" + "\n\n---\n\n".join(body_parts) + "\n"
        prepared.append(PlannedChange(f"{relative_package}/Kapitel/{chunk_name}", "create", None,
                                      chunk.encode("utf-8")))
        chunks.append(chunk_name)

    version_match = re.search(r"(?<!\d)(\d+(?:\.\d+)+)(?!\d)", Path(name).stem)
    version = version_match.group(1) if version_match else "nicht erkannt"
    note_id = _unique_id(slugify_id(f"pdf-dokumentationspaket-{Path(name).stem}"), ids)
    relative_package = package_target.relative_to(vault).as_posix()
    relative_pdf = f"{relative_package}/{name}"
    today = time.strftime("%Y-%m-%d")
    title = f"PDF-Dokumentationspaket — {Path(name).stem}"
    metadata = yaml.safe_dump({
        "id": note_id, "typ": "inboxed", "titel": title, "status": "entwurf",
        "erstellt": today, "geaendert": today,
        "quelle": f"{relative_pdf}#sha256={digest}",
        "tags": ["eingang", "doku", "paket", "pdf"],
        "paket_sha256": digest, "paket_version": version,
    }, allow_unicode=True, sort_keys=False)
    note = (
        f"---\n{metadata}---\n\n# {title}\n\n## Herkunft\n\n"
        f"- **Original-PDF:** `[[{relative_pdf}]]`\n- **SHA-256:** `{digest}`\n"
        f"- **Version:** {version}\n- **Erfasst:** {today}\n\n## Paketübersicht\n\n"
        f"- **PDF-Seiten:** {len(pages)}\n- **Markdown-Teile:** {len(chunks)}\n"
        f"- **Konvertierte Inhalte:** `[[{relative_package}/Kapitel]]`\n\n## Verarbeitungsauftrag\n\n"
        "Dieses PDF-Paket nicht als einzelne Inbox-Dateien auffächern. Das Manifest prüfen und die lokal "
        "erzeugten, seitengebundenen Markdown-Teile kontrolliert sowie versionsgebunden einpflegen.\n"
    )
    manifest = vault / "01 Inbox" / f"{note_id}.md"
    prepared.append(PlannedChange(manifest.relative_to(vault).as_posix(), "create", None,
                                  note.encode("utf-8")))
    with guard.authorize(prepared, approval=None):
        # Own this package directory exclusively so rollback cannot remove an
        # existing package. All document bytes were prepared outside the Vault.
        with _parent_directory(package_target, create=True) as directory:
            os.mkdir(package_target.name, dir_fd=directory)
            installed = []
            try:
                for change in prepared:
                    target = vault / change.relative_path
                    installed.append((target, _atomic_new_file(target, change.after_bytes)))
            except Exception:
                _rollback_installed(installed)
                # Remove only empty directories; preserve any externally added files.
                for parent in (package_target / "Kapitel", package_target):
                    try:
                        with _parent_directory(parent) as parent_fd:
                            os.rmdir(parent.name, dir_fd=parent_fd)
                    except FileNotFoundError:
                        pass
                    except OSError as exc:
                        raise RuleBlocked("PDF-Rückweg bleibt wegen fremder Dateien offen.") from exc
                raise
    return {"status": "uploaded", "filename": manifest.name, "archive": relative_package,
            "pages": len(pages), "chunks": len(chunks), "version": version, "sha256": digest}


def _inspect_zip(path: Path) -> list[zipfile.ZipInfo]:
    try:
        with zipfile.ZipFile(path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
    except zipfile.BadZipFile as exc:
        raise ValueError("Die Datei ist kein gültiges ZIP-Archiv.") from exc
    if len(infos) > MAX_ZIP_FILES:
        raise ValueError(f"Das ZIP enthält mehr als {MAX_ZIP_FILES} Dateien.")
    total = 0
    for info in infos:
        normalized = Path(info.filename)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError(f"Unsicherer ZIP-Pfad: {info.filename}")
        if info.file_size > MAX_ZIP_FILE_BYTES:
            raise ValueError(f"ZIP-Datei zu groß: {info.filename}")
        total += info.file_size
        if info.file_size / max(info.compress_size, 1) > MAX_ZIP_RATIO:
            raise ValueError(f"Verdächtige Kompressionsrate: {info.filename}")
    if total > MAX_ZIP_TOTAL_BYTES:
        raise ValueError("Das ZIP ist entpackt größer als 256 MiB.")
    return infos


def import_package(vault: Path, filename: str, content_base64: str, guard: VaultWriteGuard) -> dict:
    name = Path(filename or "").name
    if name != filename or not name.lower().endswith(".zip"):
        raise ValueError("Ein Dokumentationspaket muss eine einfache .zip-Datei sein.")
    content = _decode_archive(content_base64)
    digest = hashlib.sha256(content).hexdigest()
    ids, _, hashes = existing_vault_metadata(vault)
    if digest in hashes:
        raise FileExistsError("Dieses Dokumentationspaket ist bereits in der Vault.")

    with _temporary_input(vault, content, ".zip") as temporary:
        infos = _inspect_zip(temporary)
    markdown = [info for info in infos if info.filename.lower().endswith(".md")]
    if len(markdown) < PACKAGE_MD_THRESHOLD:
        raise ValueError(f"Paketmodus erwartet mindestens {PACKAGE_MD_THRESHOLD} Markdown-Dateien; gefunden: {len(markdown)}.")

    archive_dir = vault / "07 Anhänge" / "Dokumentationspakete"
    archive_target = archive_dir / name
    if archive_target.exists():
        archive_target = archive_dir / f"{Path(name).stem}-{digest[:12]}.zip"

    version_match = re.search(r"(?<!\d)(\d+\.\d+)(?!\d)", Path(name).stem)
    version = version_match.group(1) if version_match else "nicht erkannt"
    chapters: dict[str, int] = {}
    for info in markdown:
        parts = Path(info.filename).parts
        chapter = parts[1] if len(parts) > 2 and re.fullmatch(r"\d+\.\d+", parts[0]) else parts[0]
        chapters[chapter] = chapters.get(chapter, 0) + 1

    note_id = _unique_id(slugify_id(f"dokumentationspaket-{Path(name).stem}"), ids)
    relative_archive = archive_target.relative_to(vault).as_posix()
    source = f"{relative_archive}#sha256={digest}"
    today = time.strftime("%Y-%m-%d")
    title = f"Dokumentationspaket — {Path(name).stem}"
    metadata = yaml.safe_dump({
        "id": note_id,
        "typ": "inboxed",
        "titel": title,
        "status": "entwurf",
        "erstellt": today,
        "geaendert": today,
        "quelle": source,
        "tags": ["eingang", "doku", "paket"],
        "paket_sha256": digest,
        "paket_version": version,
    }, allow_unicode=True, sort_keys=False)
    chapter_list = "\n".join(f"- `{chapter}`: {count} Markdown-Dateien" for chapter, count in sorted(chapters.items()))
    note = (
        f"---\n{metadata}---\n\n# {title}\n\n## Herkunft\n\n"
        f"- **Unverändertes Archiv:** `[[{relative_archive}]]`\n- **SHA-256:** `{digest}`\n"
        f"- **Version:** {version}\n- **Erfasst:** {today}\n\n## Paketübersicht\n\n"
        f"- **Markdown-Dateien:** {len(markdown)}\n"
        f"- **Unkomprimierter Markdown-Umfang:** {sum(info.file_size for info in markdown)} Byte\n\n"
        f"## Kapitel\n\n{chapter_list}\n\n## Verarbeitungsauftrag\n\n"
        "Dieses Paket nicht als einzelne Inbox-Dateien auffächern. Zuerst Manifest und Kapitelstruktur prüfen, "
        "danach nur freigegebene Kapitel kontrolliert und versionsgebunden einpflegen.\n"
    )
    manifest = vault / "01 Inbox" / f"{note_id}.md"
    prepared = [PlannedChange(relative_archive, "create", None, content),
                PlannedChange(manifest.relative_to(vault).as_posix(), "create", None,
                              note.encode("utf-8"))]
    with guard.authorize(prepared, approval=None):
        installed = _atomic_new_file(archive_target, prepared[0].after_bytes)
        try:
            _atomic_new_file(manifest, prepared[1].after_bytes)
        except Exception:
            _rollback_installed([(archive_target, installed)])
            raise
    return {
        "status": "uploaded",
        "filename": manifest.name,
        "archive": relative_archive,
        "markdown_files": len(markdown),
        "version": version,
        "sha256": digest,
    }
