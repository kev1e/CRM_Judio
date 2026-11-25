from uuid import UUID

import pytest

from crm.telegram import callbacks, texts
from crm.telegram.gateway import login_keyboard

CHALLENGE = UUID("019ab3c4-0000-7000-8000-000000000001")


def test_round_trip() -> None:
    for approve in (True, False):
        data = callbacks.encode_login_decision(CHALLENGE, approve=approve)

        assert len(data.encode()) <= 64  # Telegram's limit for callback data
        assert callbacks.parse_login_decision(data) == callbacks.LoginDecision(CHALLENGE, approve)


@pytest.mark.parametrize(
    "data",
    [
        None,
        "",
        "login",
        "login:a",
        "login:x:019ab3c4-0000-7000-8000-000000000001",
        "other:a:019ab3c4-0000-7000-8000-000000000001",
        "login:a:not-a-uuid",
        "login:a:019AB3C4-0000-7000-8000-000000000001",
        "login:a:019ab3c400007000800000000000000 1",
        "login:a:019ab3c4-0000-7000-8000-000000000001:extra",
        "login:a:" + "0" * 80,
    ],
)
def test_anything_else_is_not_a_decision(data: str | None) -> None:
    assert callbacks.parse_login_decision(data) is None


def test_keyboard_has_approve_and_deny_for_this_challenge() -> None:
    (row,) = login_keyboard(CHALLENGE).inline_keyboard

    assert [button.text for button in row] == [texts.BUTTON_APPROVE, texts.BUTTON_DENY]
    decisions = [callbacks.parse_login_decision(button.callback_data) for button in row]
    assert decisions == [
        callbacks.LoginDecision(CHALLENGE, approve=True),
        callbacks.LoginDecision(CHALLENGE, approve=False),
    ]
