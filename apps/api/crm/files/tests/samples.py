"""Tiny files of each accepted type, built in memory."""

import io
import zipfile

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64


def archive(entries: dict[str, bytes], *, compress: bool = False) -> bytes:
    buffer = io.BytesIO()
    method = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(buffer, "w", method) as target:
        for name, content in entries.items():
            target.writestr(name, content)
    return buffer.getvalue()


ZIP = archive({"readme.txt": b"hello"})
DOCX = archive({"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<w:document/>"})
XLSX = archive({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<workbook/>"})
DOCX_WITH_MACROS = archive(
    {
        "[Content_Types].xml": b"<Types/>",
        "word/document.xml": b"<w:document/>",
        "word/vbaProject.bin": b"\x00",
    }
)
ZIP_BOMB = archive({"zeros.bin": b"\x00" * (4 * 1024 * 1024)}, compress=True)
