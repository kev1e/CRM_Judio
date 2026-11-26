"""What somebody typed into a request form, checked against the published
version of the form (D009, Q21). One implementation for the website and for
Telegram: no client decides what a valid value is.

Anything the form does not define is refused, never stored. A refusal names the
field and a reason and repeats nothing of what was typed.
"""

from collections.abc import Collection, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from crm.common.exceptions import DomainError

MAX_REFERENCE = 200
_MAX_NUMBER = Decimal("1e15")


class FormValueError(DomainError):
    def __init__(self, field: str, reason: str) -> None:
        super().__init__(
            "invalid_form_value",
            "A value of the form was refused.",
            {"field": field, "reason": reason},
        )


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _text(field: Mapping[str, Any], value: Any) -> str:
    if not isinstance(value, str):
        raise FormValueError(field["key"], "invalid")
    if field.get("multiline"):
        clean = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    else:
        clean = " ".join(value.split())
    limit = field.get("max_length", MAX_REFERENCE)
    if len(clean) > limit:
        raise FormValueError(field["key"], "too_long")
    if "\x00" in clean:
        raise FormValueError(field["key"], "invalid")
    return clean


def _number(field: Mapping[str, Any], value: Any) -> str:
    key = field["key"]
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise FormValueError(key, "invalid")
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation:
        raise FormValueError(key, "invalid") from None
    if not number.is_finite() or abs(number) >= _MAX_NUMBER:
        raise FormValueError(key, "invalid")
    exponent = number.as_tuple().exponent
    places = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    if field.get("integer") and number != number.to_integral_value():
        raise FormValueError(key, "not_integer")
    # Money has at most two decimal places; other numbers at most six.
    if places > (2 if field.get("currency") else 6) and number != number.to_integral_value():
        raise FormValueError(key, "too_precise")
    low, high = field.get("min"), field.get("max")
    if (low is not None and number < Decimal(str(low))) or (
        high is not None and number > Decimal(str(high))
    ):
        raise FormValueError(key, "out_of_range")
    if field.get("currency"):
        # Money is always kept with two decimal places.
        return format(number.quantize(Decimal("0.01")), "f")
    if number == number.to_integral_value():
        return str(int(number))
    return format(number.normalize(), "f")


def _date(field: Mapping[str, Any], value: Any) -> str:
    key = field["key"]
    if not isinstance(value, str):
        raise FormValueError(key, "invalid")
    try:
        if field.get("with_time"):
            moment = datetime.fromisoformat(value)
            if moment.tzinfo is None:
                raise ValueError
            moment = moment.astimezone(UTC).replace(microsecond=0)
            year, clean = moment.year, moment.isoformat().replace("+00:00", "Z")
        else:
            if len(value) != 10:
                raise ValueError
            day = date.fromisoformat(value)
            year, clean = day.year, day.isoformat()
    except ValueError, OverflowError:
        raise FormValueError(key, "invalid") from None
    if not 1900 <= year <= 2200:
        raise FormValueError(key, "out_of_range")
    return clean


def _select(field: Mapping[str, Any], value: Any) -> str | list[str]:
    key, options = field["key"], field["options"]
    if not field.get("multiple"):
        if not isinstance(value, str) or value not in options:
            raise FormValueError(key, "not_an_option")
        return value
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or item not in options for item in value)
        or len(set(value)) != len(value)
    ):
        raise FormValueError(key, "not_an_option")
    return [option for option in options if option in value]


def _employee(field: Mapping[str, Any], value: Any, people: Collection[UUID]) -> str:
    try:
        person = UUID(value) if isinstance(value, str) else None
    except ValueError:
        person = None
    # Somebody outside the request's department is refused exactly like a
    # made-up identifier: the form is no way to learn who exists.
    if person is None or person not in people:
        raise FormValueError(field["key"], "not_an_option")
    return str(person)


def clean_values(
    fields: list[dict[str, Any]],
    raw: Any,
    *,
    file_keys: Collection[str],
    people: Collection[UUID],
) -> dict[str, Any]:
    """The values to store, without the files (their keys are checked here, the
    files themselves by the rules of attachments).

    `people` — identifiers of those an `employee` field may name: the active
    employees and managers of the request's department.
    """
    if not isinstance(raw, dict):
        raise DomainError("invalid_form", "The values of a form must be an object.")
    by_key = {field["key"]: field for field in fields}
    for key in raw:
        if key not in by_key:
            raise FormValueError(str(key)[:40], "unknown_field")
    for key in file_keys:
        if key not in by_key or by_key[key]["type"] != "file":
            raise FormValueError(str(key)[:40], "unknown_field")

    clean: dict[str, Any] = {}
    for key, field in by_key.items():
        kind = field["type"]
        if kind == "file":
            if not _empty(raw.get(key)):
                # A file arrives as a file, never as a value somebody typed.
                raise FormValueError(key, "invalid")
            if field["required"] and key not in file_keys:
                raise FormValueError(key, "required")
            continue
        value = raw.get(key)
        if isinstance(value, str) and not value.strip():
            value = None
        if _empty(value):
            if field["required"]:
                raise FormValueError(key, "required")
            continue
        if kind in ("text", "reference"):
            result: Any = _text(field, value)
        elif kind == "number":
            result = _number(field, value)
        elif kind == "date":
            result = _date(field, value)
        elif kind == "select":
            result = _select(field, value)
        elif kind == "employee":
            result = _employee(field, value, people)
        elif kind == "boolean":
            if not isinstance(value, bool):
                raise FormValueError(key, "invalid")
            result = value
        else:  # pragma: no cover - `schema.clean_fields` admits no other type
            raise FormValueError(key, "invalid")
        clean[key] = result
    return clean
