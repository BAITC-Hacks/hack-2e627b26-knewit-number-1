from __future__ import annotations

import re
import struct
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree

from django.conf import settings

from catalog.safety import sanitize_text


class AttachmentError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


_TYPES = {
    "pdf": {"application/pdf"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    "jpeg": {"image/jpeg", "image/pjpeg"},
}
_EXTENSION_TO_KIND = {"pdf": "pdf", "docx": "docx", "xlsx": "xlsx", "jpg": "jpeg", "jpeg": "jpeg"}
_ZIP_SIGNATURE = b"PK\x03\x04"
_PDF_SIGNATURE = b"%PDF-"
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _limit_text(value: Any, maximum: int | None = None) -> str:
    limit = maximum or settings.ATTACHMENT_MAX_EXTRACTED_CHARS
    clean = sanitize_text(value).replace("\r", "\n")
    clean = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", clean)
    return clean[:limit].strip()


def _file_name(uploaded: Any) -> tuple[str, str]:
    raw_name = str(getattr(uploaded, "name", ""))
    name = _limit_text(Path(raw_name.replace("\\", "/")).name, settings.ATTACHMENT_MAX_FILENAME_CHARS)
    extension = name.rsplit(".", 1)[-1].casefold() if "." in name else ""
    kind = _EXTENSION_TO_KIND.get(extension)
    if not name or kind is None:
        raise AttachmentError("unsupported_file_type", "Only PDF, DOCX, XLSX and JPEG files are supported")
    return name, kind


def _declared_type(uploaded: Any, kind: str) -> str:
    value = str(getattr(uploaded, "content_type", "") or "").split(";", 1)[0].strip().casefold()
    if value not in _TYPES[kind]:
        raise AttachmentError("invalid_file_type", "The declared file type does not match its extension")
    return value


def _copy_to_temp(uploaded: Any, suffix: str) -> tuple[Path, int]:
    temp_file = tempfile.NamedTemporaryFile(prefix="ekt-upload-", suffix=f".{suffix}", delete=False)
    path = Path(temp_file.name)
    size = 0
    try:
        with temp_file:
            for chunk in uploaded.chunks():
                if not isinstance(chunk, bytes):
                    raise AttachmentError("invalid_file", "The upload contains an invalid data chunk")
                size += len(chunk)
                if size > settings.ATTACHMENT_MAX_BYTES:
                    raise AttachmentError("attachment_too_large", "The attachment exceeds the allowed size", status_code=413)
                temp_file.write(chunk)
        if not size:
            raise AttachmentError("empty_file", "The attachment is empty")
        return path, size
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _zip_members(path: Path, required: set[str]) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise AttachmentError("invalid_file_signature", "The Office document is not a valid ZIP package") from exc
    total = 0
    try:
        infos = archive.infolist()
        if not infos or len(infos) > settings.ATTACHMENT_MAX_ARCHIVE_MEMBERS:
            raise AttachmentError("unsafe_archive", "The Office archive has too many entries")
        names: set[str] = set()
        for info in infos:
            name = info.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            if not name or name.startswith("/") or ".." in parts or info.is_dir() or info.flag_bits & 0x1:
                raise AttachmentError("unsafe_archive", "The Office archive contains an unsafe entry")
            if info.file_size > settings.ATTACHMENT_MAX_ARCHIVE_MEMBER_BYTES:
                raise AttachmentError("unsafe_archive", "The Office archive contains an oversized entry")
            total += info.file_size
            if total > settings.ATTACHMENT_MAX_UNCOMPRESSED_BYTES:
                raise AttachmentError("unsafe_archive", "The Office archive expands beyond the allowed limit")
            if info.file_size and not info.compress_size:
                raise AttachmentError("unsafe_archive", "The Office archive contains an invalid compressed entry")
            if info.file_size > max(1, info.compress_size) * settings.ATTACHMENT_MAX_COMPRESSION_RATIO:
                raise AttachmentError("unsafe_archive", "The Office archive compression ratio is unsafe")
            lowered = name.casefold()
            if "vbaproject.bin" in lowered or "/activex/" in lowered:
                raise AttachmentError("active_content_not_allowed", "Macro or active content is not allowed")
            names.add(name)
        if not required.issubset(names):
            raise AttachmentError("invalid_file_signature", "The Office document structure does not match its extension")
        content_types = archive.read("[Content_Types].xml").decode("utf-8", "replace").casefold()
        if "macroenabled" in content_types or "vba" in content_types:
            raise AttachmentError("active_content_not_allowed", "Macro or active content is not allowed")
        return archive
    except Exception:
        archive.close()
        raise


def _office_metadata(archive: zipfile.ZipFile) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if "docProps/core.xml" not in archive.namelist():
        return metadata
    root = _xml_root(archive.read("docProps/core.xml"))
    fields = {"title", "subject", "creator", "description", "created", "modified"}
    for element in root.iter():
        key = element.tag.rsplit("}", 1)[-1]
        if key in fields and element.text:
            value = _limit_text(element.text, 300)
            if value:
                metadata[key] = value
    return metadata


def _xml_root(payload: bytes) -> ElementTree.Element:
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise AttachmentError("unsafe_xml", "The Office document contains unsafe XML declarations")
    try:
        return ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise AttachmentError("invalid_file", "The Office document contains invalid XML") from exc


def _extract_docx(path: Path) -> tuple[str, dict[str, Any]]:
    archive = _zip_members(path, {"[Content_Types].xml", "word/document.xml"})
    try:
        root = _xml_root(archive.read("word/document.xml"))
        text = _limit_text("\n".join(piece.strip() for piece in root.itertext() if piece and piece.strip()))
        metadata = _office_metadata(archive)
        metadata["format"] = "docx"
        return text, metadata
    finally:
        archive.close()


def _extract_xlsx(path: Path) -> tuple[str, dict[str, Any]]:
    archive = _zip_members(path, {"[Content_Types].xml", "xl/workbook.xml"})
    try:
        sheet_names = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml"))
        if not sheet_names:
            raise AttachmentError("invalid_file_signature", "The XLSX document contains no worksheets")
        pieces: list[str] = []
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = _xml_root(archive.read("xl/sharedStrings.xml"))
            shared = [_limit_text("".join(item.itertext()), 1000) for item in shared_root if _limit_text("".join(item.itertext()), 1000)]
        for sheet_name in sheet_names:
            root = _xml_root(archive.read(sheet_name))
            values: list[str] = []
            for cell in root.iter():
                if cell.tag.rsplit("}", 1)[-1] != "c":
                    continue
                value = next((child.text for child in cell if child.tag.rsplit("}", 1)[-1] == "v"), None)
                if not value:
                    continue
                if cell.attrib.get("t") == "s" and value.isdigit() and int(value) < len(shared):
                    values.append(shared[int(value)])
                else:
                    values.append(value)
            if values:
                pieces.append(f"{Path(sheet_name).stem}: " + " | ".join(values))
        metadata = _office_metadata(archive)
        metadata.update({"format": "xlsx", "sheets": len(sheet_names)})
        return _limit_text("\n".join(pieces)), metadata
    finally:
        archive.close()


def _extract_pdf(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            raise AttachmentError("encrypted_file", "Encrypted PDF files are not supported")
        if len(reader.pages) > settings.ATTACHMENT_MAX_PDF_PAGES:
            raise AttachmentError("document_too_large", "The PDF has too many pages")
        text = _limit_text("\n".join(page.extract_text() or "" for page in reader.pages))
        metadata: dict[str, Any] = {"format": "pdf", "pages": len(reader.pages)}
        document_info = reader.metadata
        for name in ("title", "author", "subject", "creator", "producer"):
            value = getattr(document_info, name, None) if document_info else None
            if value:
                metadata[name] = _limit_text(value, 300)
        return text, metadata
    except AttachmentError:
        raise
    except Exception as exc:
        raise AttachmentError("invalid_file", "The PDF could not be safely read") from exc


def _extract_jpeg(path: Path) -> tuple[str, dict[str, Any]]:
    data = path.read_bytes()
    if not data.startswith(_JPEG_SIGNATURE):
        raise AttachmentError("invalid_file_signature", "The JPEG signature does not match the file")
    position = 2
    width = height = None
    comments: list[str] = []
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            break
        marker = data[position]
        position += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if position + 2 > len(data):
            raise AttachmentError("invalid_file", "The JPEG segment is incomplete")
        segment_length = struct.unpack(">H", data[position : position + 2])[0]
        if segment_length < 2 or position + segment_length > len(data):
            raise AttachmentError("invalid_file", "The JPEG segment is invalid")
        payload = data[position + 2 : position + segment_length]
        if marker in _SOF_MARKERS and len(payload) >= 5:
            height, width = struct.unpack(">HH", payload[1:5])
        elif marker == 0xFE:
            comment = _limit_text(payload.decode("utf-8", "replace"), 500)
            if comment:
                comments.append(comment)
        if marker == 0xDA:
            break
        position += segment_length
    if not width or not height:
        raise AttachmentError("invalid_file", "The JPEG dimensions could not be read")
    metadata: dict[str, Any] = {"format": "jpeg", "width": width, "height": height}
    return _limit_text("\n".join(comments)), metadata


def extract_attachment(uploaded: Any) -> dict[str, Any]:
    """Validate, parse and delete an uploaded file; never persist its raw bytes."""
    path: Path | None = None
    try:
        name, kind = _file_name(uploaded)
        declared_type = _declared_type(uploaded, kind)
        path, size = _copy_to_temp(uploaded, kind)
        with path.open("rb") as source:
            header = source.read(8)
        if kind == "pdf":
            if not header.startswith(_PDF_SIGNATURE):
                raise AttachmentError("invalid_file_signature", "The PDF signature does not match the file")
            text, metadata = _extract_pdf(path)
        elif kind == "jpeg":
            text, metadata = _extract_jpeg(path)
        else:
            if not header.startswith(_ZIP_SIGNATURE):
                raise AttachmentError("invalid_file_signature", "The Office signature does not match the file")
            text, metadata = _extract_docx(path) if kind == "docx" else _extract_xlsx(path)
        return {
            "name": name,
            "size": size,
            "type": declared_type,
            "metadata": metadata,
            "text": text,
        }
    finally:
        try:
            close = getattr(uploaded, "close", None)
            if callable(close):
                close()
        finally:
            if path is not None:
                path.unlink(missing_ok=True)
