"""D036: the bot hands out the one-time link for choosing the first password."""

import pytest

from crm.common.actors import Actor
from crm.conftest import STRONG_PASSWORD, Employee, UserFactory
from crm.identity import enrollment, password_setup
from crm.identity.models import PasswordSetupToken
from crm.telegram import texts

from .telegram import SendMessage, feed, message_update

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

TG_ID = 555000111


def link_from(text: str) -> str:
    return next(line for line in text.splitlines() if "/set-password#" in line)


def test_binding_a_passwordless_account_is_followed_by_the_link(
    make_user: UserFactory, admin_actor: Actor
) -> None:
    user = make_user("ivan.petrov")
    code = enrollment.issue_token(actor=admin_actor, user=user)

    session = feed(message_update(f"/start {code.value}", user_id=TG_ID))

    done, link_message = session.of(SendMessage)
    assert done.text == texts.ENROLLMENT_DONE
    assert link_message.chat_id == TG_ID
    assert link_message.protect_content is True
    assert link_message.link_preview_options.is_disabled is True
    raw_token = link_from(link_message.text).split("#", 1)[1]
    password_setup.set_initial_password(
        raw_token=raw_token, password=STRONG_PASSWORD, ip_address=None
    )
    user.refresh_from_db()
    assert user.check_password(STRONG_PASSWORD)


def test_no_link_when_the_account_already_has_a_password(
    make_user: UserFactory, admin_actor: Actor
) -> None:
    user = make_user("with.password", password=STRONG_PASSWORD)
    code = enrollment.issue_token(actor=admin_actor, user=user)

    session = feed(message_update(f"/start {code.value}", user_id=TG_ID))

    assert session.texts(SendMessage) == [texts.ENROLLMENT_DONE]
    assert not PasswordSetupToken.objects.exists()


def test_password_command_sends_a_fresh_link(make_user: UserFactory, admin_actor: Actor) -> None:
    code = enrollment.issue_token(actor=admin_actor, user=make_user("ivan.petrov"))
    first = feed(message_update(f"/start {code.value}", user_id=TG_ID))
    old_token = link_from(first.of(SendMessage)[1].text).split("#", 1)[1]

    session = feed(message_update("/password", user_id=TG_ID))

    (message,) = session.of(SendMessage)
    new_token = link_from(message.text).split("#", 1)[1]
    assert new_token != old_token
    with pytest.raises(password_setup.SetupLinkRejectedError):
        password_setup.set_initial_password(
            raw_token=old_token, password=STRONG_PASSWORD, ip_address=None
        )


def test_password_command_gives_nothing_to_others(employee: Employee) -> None:
    # An account with a password, and a Telegram account bound to nothing, get
    # the same answer and no link.
    for telegram_id in (employee.telegram_user_id, 999_999):
        session = feed(message_update("/password", user_id=telegram_id))

        assert session.texts(SendMessage) == [texts.SETUP_LINK_NOT_AVAILABLE]
    assert not PasswordSetupToken.objects.exists()


def test_password_command_is_ignored_in_groups(make_user: UserFactory, admin_actor: Actor) -> None:
    code = enrollment.issue_token(actor=admin_actor, user=make_user("ivan.petrov"))
    feed(message_update(f"/start {code.value}", user_id=TG_ID))
    before = PasswordSetupToken.objects.count()

    session = feed(message_update("/password", user_id=TG_ID, chat_type="supergroup"))

    assert session.calls == []
    assert PasswordSetupToken.objects.count() == before
