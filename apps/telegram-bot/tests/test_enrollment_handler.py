"""S1.2b: `/start <code>` binds the sender's numeric Telegram ID (Q11)."""

import pytest

from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.conftest import UserFactory
from crm.identity import enrollment
from crm.identity.models import User
from crm.telegram import texts

from .telegram import DeleteMessage, SendMessage, feed, message_update

# Handlers run domain code in another thread, so each test needs real commits;
# the rows created by migrations (the administrator role) are restored after each.
pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

TG_ID = 555000111


def test_start_with_a_valid_code_binds_the_sender(
    make_user: UserFactory, admin_actor: Actor
) -> None:
    user = make_user("ivan.petrov")
    token = enrollment.issue_token(actor=admin_actor, user=user)

    session = feed(message_update(f"/start {token.value}", user_id=TG_ID, username="ivan_p"))

    user.refresh_from_db()
    assert user.telegram_user_id == TG_ID
    assert user.telegram_username == "ivan_p"
    assert session.texts(SendMessage) == [texts.ENROLLMENT_DONE]
    # The message with the code is removed from the chat.
    assert [call.message_id for call in session.of(DeleteMessage)] == [10]
    assert token.value not in " ".join(session.texts(SendMessage))


def test_the_id_comes_from_telegram_not_from_the_text(
    make_user: UserFactory, admin_actor: Actor
) -> None:
    user = make_user("ivan.petrov")
    token = enrollment.issue_token(actor=admin_actor, user=user)

    feed(message_update(f"/start {token.value} 999 @boss", user_id=TG_ID))

    user.refresh_from_db()
    # Extra text made the code wrong; nothing typed by the user can name an account.
    assert user.telegram_user_id is None


@pytest.mark.parametrize("code", ["wrong-code", "x" * 300])
def test_wrong_code_gets_one_generic_answer(db: None, code: str) -> None:
    session = feed(message_update(f"/start {code}", user_id=TG_ID))

    assert session.texts(SendMessage) == [texts.ENROLLMENT_REJECTED]
    assert not User.objects.filter(telegram_user_id=TG_ID).exists()
    event = AuditEvent.objects.get(action="telegram.enrollment_rejected")
    assert event.metadata["reason"] == "unknown_token"


def test_used_code_is_refused_with_the_same_answer(
    make_user: UserFactory, admin_actor: Actor
) -> None:
    token = enrollment.issue_token(actor=admin_actor, user=make_user())
    feed(message_update(f"/start {token.value}", user_id=TG_ID))

    session = feed(message_update(f"/start {token.value}", user_id=TG_ID + 1))

    assert session.texts(SendMessage) == [texts.ENROLLMENT_REJECTED]
    assert not User.objects.filter(telegram_user_id=TG_ID + 1).exists()


def test_code_sent_in_a_group_is_ignored_silently_and_stays_valid(
    make_user: UserFactory, admin_actor: Actor
) -> None:
    user = make_user()
    token = enrollment.issue_token(actor=admin_actor, user=user)

    session = feed(message_update(f"/start {token.value}", user_id=TG_ID, chat_type="supergroup"))

    assert session.calls == []  # the bot says nothing in the group
    user.refresh_from_db()
    assert user.telegram_user_id is None
    event = AuditEvent.objects.get(action="telegram.enrollment_rejected")
    assert event.metadata["reason"] == "not_private_chat"

    feed(message_update(f"/start {token.value}", user_id=TG_ID))
    user.refresh_from_db()
    assert user.telegram_user_id == TG_ID


def test_plain_start_explains_what_to_do(db: None) -> None:
    session = feed(message_update("/start", user_id=TG_ID))

    assert session.texts(SendMessage) == [texts.START_HELP]


def test_plain_start_in_a_group_is_ignored(db: None) -> None:
    session = feed(message_update("/start", user_id=TG_ID, chat_type="group"))

    assert session.calls == []


def test_ordinary_messages_are_not_handled_or_stored(db: None) -> None:
    before = AuditEvent.objects.count()

    session = feed(message_update("Привет, как дела с заявкой?", user_id=TG_ID))

    assert session.calls == []
    assert AuditEvent.objects.count() == before
