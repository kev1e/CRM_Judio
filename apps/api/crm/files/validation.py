"""What may be uploaded (Q16): PDF, Word, Excel, images and ZIP archives, up to
100 MB. The decision is made from the file's content, not from what the browser
claims: the extension must be on the list **and** the bytes must be of that type.

Nothing is ever extracted or executed. Archives (and the Office formats that are
archives inside) are only looked at through their table of contents.

No antivirus scan is performed (Q16: not required in the first version). That
residual risk is documented in docs/SECURITY.md.

PROVISIONAL numbers (docs/OPEN_QUESTIONS.md): the archive limits below.
"""

import unicodedata
import zipfile
from dataclasses import dataclass
from typing import BinaryIO

from crm.common.exceptions import DomainError

MAX_NAME_LENGTH = 200
ZIP_MAX_ENTRIES = 10_000
ZIP_MAX_UNPACKED_BYTES = 2 * 1024**3
ZIP_MAX_RATIO = 200

_OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP = (b"PK\x03\x04", b"PK\x05\x06")
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# extension -> (content type, kind of check)
ALLOWED: dict[str, tuple[str, str]] = {
    "pdf": ("application/pdf", "pdf"),
    "png": ("image/png", "png"),
    "jpg": ("image/jpeg", "jpeg"),
    "jpeg": ("image/jpeg", "jpeg"),
    "gif": ("image/gif", "gif"),
    "webp": ("image/webp", "webp"),
    "doc": ("application/msword", "ole2"),
    "xls": ("application/vnd.ms-excel", "ole2"),
    "docx": (_DOCX, "docx"),
    "xlsx": (_XLSX, "xlsx"),
    "zip": ("application/zip", "zip"),
}


@dataclass(frozen=True, slots=True)
class Accepted:
    name: str
    extension: str
    content_type: str


def _refuse(code: str, message: str) -> DomainError:
    return DomainError(code, message)


def clean_name(raw: str) -> str:
    """The name shown to people. It never becomes part of a path or a storage key."""
    name = unicodedata.normalize("NFC", raw).replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip().strip(".")
    if not name or "." not in name:
        raise _refuse("file_type_not_allowed", "The file needs a name with an allowed extension.")
    if len(name) > MAX_NAME_LENGTH:
        stem, extension = name.rsplit(".", 1)
        name = f"{stem[: MAX_NAME_LENGTH - len(extension) - 1]}.{extension}"
    return name


def _check_archive(stream: BinaryIO, required: str | None) -> None:
    try:
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, ValueError) as error:
        raise _refuse("file_content_mismatch", "The file is damaged or is not an archive.") from (
            error
        )
    unpacked = sum(entry.file_size for entry in entries)
    packed = sum(entry.compress_size for entry in entries)
    if (
        len(entries) > ZIP_MAX_ENTRIES
        or unpacked > ZIP_MAX_UNPACKED_BYTES
        or unpacked > max(packed, 1) * ZIP_MAX_RATIO
    ):
        raise _refuse("file_archive_unsafe", "The archive unpacks to too much data.")
    names = {entry.filename for entry in entries}
    if required is not None:
        if required not in names or "[Content_Types].xml" not in names:
            raise _refuse("file_content_mismatch", "The file is not what its extension says.")
        if any(name.lower().endswith("vbaproject.bin") for name in names):
            raise _refuse("file_type_not_allowed", "Documents with macros are not accepted.")


def inspect(stream: BinaryIO, raw_name: str) -> Accepted:
    """Decide whether the file is acceptable. `stream` must be seekable; it is
    left at its start."""
    name = clean_name(raw_name)
    extension = name.rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED:
        raise _refuse(
            "file_type_not_allowed", "Only PDF, Word, Excel, images and ZIP archives are accepted."
        )
    content_type, kind = ALLOWED[extension]
    stream.seek(0)
    head = stream.read(16)
    stream.seek(0)
    if not head:
        raise _refuse("file_empty", "The file is empty.")
    matches = {
        "pdf": head.startswith(b"%PDF-"),
        "png": head.startswith(b"\x89PNG\r\n\x1a\n"),
        "jpeg": head.startswith(b"\xff\xd8\xff"),
        "gif": head.startswith((b"GIF87a", b"GIF89a")),
        "webp": head.startswith(b"RIFF") and head[8:12] == b"WEBP",
        "ole2": head.startswith(_OLE2),
        "docx": head.startswith(_ZIP),
        "xlsx": head.startswith(_ZIP),
        "zip": head.startswith(_ZIP),
    }[kind]
    if not matches:
        raise _refuse("file_content_mismatch", "The file is not what its extension says.")
    if kind in {"docx", "xlsx", "zip"}:
        _check_archive(stream, {"docx": "word/document.xml", "xlsx": "xl/workbook.xml"}.get(kind))
        stream.seek(0)
    return Accepted(name=name, extension=extension, content_type=content_type)
