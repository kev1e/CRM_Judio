"""S1.3: the approve/deny buttons of a login prompt (Q13)."""

import pytest

from crm.conftest import Employee, EmployeeFactory
from crm.identity import auth
from crm.identity.models import LoginChallenge
from crm.telegram import callbacks, texts

from .telegram import AnswerCallbackQuery, EditMessageText, callback_update, feed

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)


def start(employee: Employee) -> auth.StartedLogin:
    return auth.start_login(
        crm_login=employee.user.crm_login,
        password=employee.password,
        ip_address="203.0.113.5",
        user_agent="tests",
    )


def press(started: auth.StartedLogin, *, user_id: int, approve: bool = True):  # type: ignore[no-untyped-def]
    data = callbacks.encode_login_decision(started.challenge_id, approve=approve)
    return feed(callback_update(data, user_id=user_id))


def status(started: auth.StartedLogin) -> str:
    return LoginChallenge.objects.get(pk=started.challenge_id).status


def test_approve_button_approves_and_removes_the_buttons(employee: Employee) -> None:
    started = start(employee)

    session = press(started, user_id=employee.telegram_user_id)

    assert status(started) == "approved"
    assert session.texts(AnswerCallbackQuery) == [texts.LOGIN_APPROVED]
    (edit,) = session.of(EditMessageText)
    assert edit.text == texts.LOGIN_APPROVED
    assert edit.reply_markup is None
    progress = auth.complete_login(
        challenge_id=started.challenge_id,
        attempt_key=started.attempt_key,
        ip_address=None,
        user_agent=None,
    )
    assert progress.state is auth.LoginState.AUTHENTICATED


def test_deny_button_denies(employee: Employee) -> None:
    started = start(employee)

    session = press(started, user_id=employee.telegram_user_id, approve=False)

    assert status(started) == "denied"
    assert session.texts(AnswerCallbackQuery) == [texts.LOGIN_DENIED]


def test_button_pressed_by_another_telegram_account_changes_nothing(
    employee: Employee, make_employee: EmployeeFactory
) -> None:
    colleague = make_employee("boris.ivanov")
    started = start(employee)

    session = press(started, user_id=colleague.telegram_user_id)

    assert status(started) == "pending"
    assert session.texts(AnswerCallbackQuery) == [texts.LOGIN_NOT_VALID]


def test_second_press_is_refused(employee: Employee) -> None:
    started = start(employee)
    press(started, user_id=employee.telegram_user_id)

    session = press(started, user_id=employee.telegram_user_id, approve=False)

    assert status(started) == "approved"
    assert session.texts(AnswerCallbackQuery) == [texts.LOGIN_NOT_VALID]


@pytest.mark.parametrize("data", ["login:a:not-a-uuid", "login:zzz", "login:"])
def test_forged_callback_data_is_refused(employee: Employee, data: str) -> None:
    started = start(employee)

    session = feed(callback_update(data, user_id=employee.telegram_user_id))

    assert status(started) == "pending"
    assert session.texts(AnswerCallbackQuery) == [texts.LOGIN_NOT_VALID]


def test_unrelated_callback_is_ignored(employee: Employee) -> None:
    session = feed(callback_update("something:else", user_id=employee.telegram_user_id))

    assert session.calls == []
