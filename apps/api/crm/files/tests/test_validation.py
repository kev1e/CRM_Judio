"""Q16: only allowlisted types, judged by content; unsafe archives refused."""

import io

import pytest

from crm.common.exceptions import DomainError
from crm.files import validation
from crm.files.tests import samples


def check(content: bytes, name: str) -> validation.Accepted:
    return validation.inspect(io.BytesIO(content), name)


@pytest.mark.parametrize(
    ("content", "name", "content_type"),
    [
        (samples.PDF, "Договор.pdf", "application/pdf"),
        (samples.PNG, "scan.PNG", "image/png"),
        (samples.JPEG, "photo.jpg", "image/jpeg"),
        (samples.JPEG, "photo.jpeg", "image/jpeg"),
        (samples.GIF, "anim.gif", "image/gif"),
        (samples.WEBP, "pic.webp", "image/webp"),
        (samples.OLE2, "old.doc", "application/msword"),
        (samples.OLE2, "old.xls", "application/vnd.ms-excel"),
        (
            samples.DOCX,
            "letter.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            samples.XLSX,
            "table.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (samples.ZIP, "files.zip", "application/zip"),
    ],
)
def test_allowed_types_are_recognized_by_content(
    content: bytes, name: str, content_type: str
) -> None:
    stream = io.BytesIO(content)
    accepted = validation.inspect(stream, name)
    assert accepted.content_type == content_type
    assert accepted.name == name
    assert stream.tell() == 0


@pytest.mark.parametrize(
    "name",
    ["run.exe", "page.html", "image.svg", "script.js", "macro.docm", "book.xlsm", "movie.mp4",
     "archive.rar", "noextension", ".pdf", ""],
)  # fmt: skip
def test_other_extensions_are_refused(name: str) -> None:
    with pytest.raises(DomainError) as error:
        check(samples.PDF, name)
    assert error.value.code == "file_type_not_allowed"


@pytest.mark.parametrize(
    ("content", "name"),
    [
        (b"MZ\x90\x00" + b"\x00" * 60, "invoice.pdf"),  # an executable renamed
        (b"<html><script>alert(1)</script></html>", "photo.png"),
        (samples.PNG, "photo.jpg"),
        (samples.ZIP, "letter.docx"),  # an archive that is not a document
        (samples.DOCX, "table.xlsx"),
        (samples.PDF, "files.zip"),
        (b"PK\x03\x04 broken", "files.zip"),
    ],
)
def test_content_that_does_not_match_the_extension_is_refused(content: bytes, name: str) -> None:
    with pytest.raises(DomainError) as error:
        check(content, name)
    assert error.value.code == "file_content_mismatch"


def test_empty_file_is_refused() -> None:
    with pytest.raises(DomainError) as error:
        check(b"", "empty.pdf")
    assert error.value.code == "file_empty"


def test_document_with_macros_is_refused() -> None:
    with pytest.raises(DomainError) as error:
        check(samples.DOCX_WITH_MACROS, "letter.docx")
    assert error.value.code == "file_type_not_allowed"


def test_archive_bomb_is_refused_without_unpacking() -> None:
    assert len(samples.ZIP_BOMB) < 10_000
    with pytest.raises(DomainError) as error:
        check(samples.ZIP_BOMB, "bomb.zip")
    assert error.value.code == "file_archive_unsafe"


def test_archive_with_too_many_entries_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validation, "ZIP_MAX_ENTRIES", 2)
    content = samples.archive({f"{i}.txt": b"x" for i in range(3)})
    with pytest.raises(DomainError) as error:
        check(content, "many.zip")
    assert error.value.code == "file_archive_unsafe"


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\anna\\Договор.pdf", "Договор.pdf"),
        ("a\x00b\r\n.pdf", "ab.pdf"),
        ("  report.pdf  ", "report.pdf"),
        ("x" * 300 + ".pdf", "x" * 196 + ".pdf"),
    ],
)
def test_names_are_reduced_to_a_safe_display_name(raw: str, clean: str) -> None:
    assert validation.clean_name(raw) == clean
