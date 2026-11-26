"""The shape of a request form: its fields and what each may contain (D009).

Eight field types (PRD §5):

    text       one line or several
    number     a number, optionally money with a currency code
    date       a date, optionally with time
    select     one or several of the listed options
    employee   an employee of the request's department
    file       a file, under the rules of attachments (Q16)
    boolean    yes / no
    reference  a link to a record of another system

`clean_fields` turns what the administrator typed into the canonical form that is
stored and published; anything it does not know is refused, never kept. The same
definitions drive the validation of submitted values (S5, next slice), on the
web and in Telegram alike.

PROVISIONAL (docs/OPEN_QUESTIONS.md): `reference` holds a short text identifier
of an external record — which systems and how they are checked is not decided
(Q27). Limits on counts and lengths below are engineering limits.
"""

import re
from typing import Any

from crm.common.exceptions import DomainError

FIELD_TYPES = ("text", "number", "date", "select", "employee", "file", "boolean", "reference")
MAX_FIELDS = 50
MAX_OPTIONS = 50
MAX_CHECKPOINTS = 30
MAX_LABEL = 120
MAX_HELP = 300
MAX_TEXT_LENGTH = 5000
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_COMMON = {"key", "type", "label", "required", "help"}
_OPTIONS: dict[str, set[str]] = {
    "text": {"multiline", "max_length"},
    "number": {"integer", "min", "max", "currency"},
    "date": {"with_time"},
    "select": {"options", "multiple"},
    "employee": set(),
    "file": set(),
    "boolean": set(),
    "reference": set(),
}


class SchemaError(DomainError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__("invalid_template", message)
        self.field = field


def _text(value: Any, what: str, limit: int, *, field: str | None, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise SchemaError(f"{what} must be text.", field=field)
    clean = " ".join(value.split())
    if (required and not clean) or len(clean) > limit:
        raise SchemaError(f"{what} must have 1 to {limit} characters.", field=field)
    return clean


def _flag(raw: dict[str, Any], name: str, *, field: str) -> bool:
    value = raw.get(name, False)
    if not isinstance(value, bool):
        raise SchemaError(f"“{name}” must be true or false.", field=field)
    return value


def _number(raw: dict[str, Any], name: str, *, field: str) -> int | float | None:
    value = raw.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SchemaError(f"“{name}” must be a number.", field=field)
    if value != value or value in (float("inf"), float("-inf")):
        raise SchemaError(f"“{name}” must be a finite number.", field=field)
    return value


def _clean_field(raw: Any, seen: set[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SchemaError("A field must be an object.")
    key = raw.get("key")
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise SchemaError(
            "A field key is 1–40 lowercase Latin letters, digits or “_”, starting with a letter."
        )
    if key in seen:
        raise SchemaError("Field keys must be unique.", field=key)
    seen.add(key)
    kind = raw.get("type")
    if kind not in FIELD_TYPES:
        raise SchemaError("Unknown field type.", field=key)
    unknown = set(raw) - _COMMON - _OPTIONS[kind]
    if unknown:
        raise SchemaError(f"Unknown setting: {sorted(unknown)[0]}.", field=key)

    field: dict[str, Any] = {
        "key": key,
        "type": kind,
        "label": _text(raw.get("label"), "A field label", MAX_LABEL, field=key),
        "required": _flag(raw, "required", field=key),
        "help": _text(raw.get("help"), "A field hint", MAX_HELP, field=key, required=False),
    }
    if kind == "text":
        field["multiline"] = _flag(raw, "multiline", field=key)
        limit = raw.get("max_length", 500 if not field["multiline"] else MAX_TEXT_LENGTH)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_TEXT_LENGTH
        ):
            raise SchemaError(f"“max_length” must be 1 to {MAX_TEXT_LENGTH}.", field=key)
        field["max_length"] = limit
    elif kind == "number":
        field["integer"] = _flag(raw, "integer", field=key)
        low, high = _number(raw, "min", field=key), _number(raw, "max", field=key)
        if low is not None and high is not None and low > high:
            raise SchemaError("“min” must not exceed “max”.", field=key)
        field["min"], field["max"] = low, high
        currency = raw.get("currency")
        if currency is not None and (
            not isinstance(currency, str) or not _CURRENCY.fullmatch(currency)
        ):
            raise SchemaError("A currency is a three-letter code such as RUB.", field=key)
        field["currency"] = currency
    elif kind == "date":
        field["with_time"] = _flag(raw, "with_time", field=key)
    elif kind == "select":
        field["multiple"] = _flag(raw, "multiple", field=key)
        options = raw.get("options")
        if not isinstance(options, list) or not 1 <= len(options) <= MAX_OPTIONS:
            raise SchemaError(f"A list needs 1 to {MAX_OPTIONS} options.", field=key)
        labels = [_text(option, "An option", MAX_LABEL, field=key) for option in options]
        if len({label.casefold() for label in labels}) != len(labels):
            raise SchemaError("Options must differ.", field=key)
        field["options"] = labels
    return field


def clean_fields(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise SchemaError("Fields must be a list.")
    if len(raw) > MAX_FIELDS:
        raise SchemaError(f"A form has at most {MAX_FIELDS} fields.")
    seen: set[str] = set()
    return [_clean_field(item, seen) for item in raw]


def clean_checkpoints(raw: Any) -> list[str]:
    """Checkpoints a new request starts with (D006)."""
    if not isinstance(raw, list):
        raise SchemaError("Checkpoints must be a list.")
    if len(raw) > MAX_CHECKPOINTS:
        raise SchemaError(f"A form has at most {MAX_CHECKPOINTS} checkpoints.")
    return [_text(item, "A checkpoint", 200, field=None) for item in raw]
