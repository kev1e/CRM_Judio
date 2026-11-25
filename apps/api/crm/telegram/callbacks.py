"""Callback data of inline buttons. Telegram limits it to 64 bytes.

The data carries no secret and proves nothing: the decision is authorized by the
numeric ID of the Telegram account that pressed the button, which Telegram supplies.
"""

from dataclasses import dataclass
from uuid import UUID

_PREFIX = "login"
_APPROVE = "a"
_DENY = "d"


@dataclass(frozen=True, slots=True)
class LoginDecision:
    challenge_id: UUID
    approve: bool


def encode_login_decision(challenge_id: UUID, *, approve: bool) -> str:
    return f"{_PREFIX}:{_APPROVE if approve else _DENY}:{challenge_id}"


def parse_login_decision(data: str | None) -> LoginDecision | None:
    """None for anything that is not exactly a login decision produced by this module."""
    if not data or len(data) > 64:
        return None
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != _PREFIX or parts[1] not in (_APPROVE, _DENY):
        return None
    try:
        challenge_id = UUID(parts[2])
    except ValueError:
        return None
    if str(challenge_id) != parts[2]:
        return None
    return LoginDecision(challenge_id=challenge_id, approve=parts[1] == _APPROVE)
