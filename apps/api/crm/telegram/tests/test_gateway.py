from datetime import UTC, datetime
from uuid import UUID

import pytest
from pytest_django.fixtures import Settings

from crm.telegram import gateway, texts
from crm.telegram.fake import FakeGateway

PROMPT = gateway.LoginPrompt(
    chat_id=700001,
    challenge_id=UUID("019ab3c4-0000-7000-8000-000000000001"),
    crm_login="anna.petrova",
    ip_address="203.0.113.5",
    user_agent="<b>Mozilla</b>",
    expires_at=datetime(2026, 11, 25, 12, 30, 45, tzinfo=UTC),
)


def test_default_gateway_is_the_bot_api(settings: Settings) -> None:
    settings.TELEGRAM_GATEWAY = "crm.telegram.gateway.AiogramGateway"

    assert isinstance(gateway.get_gateway(), gateway.AiogramGateway)


def test_tests_never_use_the_real_gateway() -> None:
    assert isinstance(gateway.get_gateway(), FakeGateway)


@pytest.mark.parametrize("token", ["", "not-a-bot-token"])
def test_missing_or_malformed_bot_token_is_a_permanent_refusal(
    settings: Settings, token: str
) -> None:
    settings.TELEGRAM_BOT_TOKEN = token

    with pytest.raises(gateway.TelegramRefusedError) as error:
        gateway.AiogramGateway().send_login_prompt(PROMPT)

    assert token == "" or token not in str(error.value)


def test_prompt_text_names_the_account_and_the_source() -> None:
    text = texts.login_prompt(
        crm_login=PROMPT.crm_login,
        ip_address=PROMPT.ip_address,
        user_agent=PROMPT.user_agent,
        expires_at=PROMPT.expires_at,
    )

    assert "anna.petrova" in text
    assert "203.0.113.5" in text
    assert "12:30:45 UTC" in text
    # Client-supplied text is shown as is; the message is sent without a parse mode.
    assert "<b>Mozilla</b>" in text


def test_bot_talks_to_telegram_by_default(settings: Settings) -> None:
    from crm.telegram.client import build_bot

    bot = build_bot("42:TEST-TOKEN-NOT-REAL")

    assert bot.session.api.base.startswith("https://api.telegram.org/")


def test_bot_api_address_can_point_to_a_relay(settings: Settings) -> None:
    from crm.telegram.client import build_bot

    settings.TELEGRAM_API_BASE_URL = "http://bot-api.internal:8081"

    bot = build_bot("42:TEST-TOKEN-NOT-REAL")

    assert bot.session.api.api_url(token="T", method="getMe") == (
        "http://bot-api.internal:8081/botT/getMe"
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://crm.example.com/set-password#t", True),
        ("http://127.0.0.1:3000/set-password#t", True),
        ("http://[::1]:3000/x", True),
        ("http://localhost:3000/set-password#t", False),
        ("http://crm/set-password", False),
        ("not a url", False),
    ],
)
def test_only_addresses_telegram_accepts_are_linkable(url: str, expected: bool) -> None:
    assert gateway.is_linkable(url) is expected
