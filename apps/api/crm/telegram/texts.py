"""Texts the bot sends. Russian is the default language of the CRM; the texts are
kept in one module so they can move to a message catalogue with the other locales.

Everything is sent as plain text (no parse mode): values such as the browser
description come from the client and must never be interpreted as markup.
"""

from datetime import datetime

BUTTON_APPROVE = "Подтвердить вход"
BUTTON_DENY = "Отклонить"

START_HELP = (
    "Это бот корпоративной CRM.\n\n"
    "Чтобы привязать Telegram к учётной записи, отправьте сюда код привязки, "
    "который вам выдал администратор:\n/start КОД"
)
ENROLLMENT_DONE = (
    "Готово: Telegram привязан к учётной записи CRM. "
    "Сюда будут приходить запросы на подтверждение входа."
)
ENROLLMENT_REJECTED = (
    "Код привязки недействителен или его срок истёк. Попросите администратора выдать новый код."
)

LOGIN_APPROVED = "Вход подтверждён. Вернитесь на страницу CRM."
LOGIN_DENIED = "Вход отклонён. Если вы не пытались войти, смените пароль и сообщите администратору."
LOGIN_NOT_VALID = "Запрос на вход уже недействителен или его срок истёк."
TEMPORARY_FAILURE = "Не удалось выполнить действие. Попробуйте ещё раз."


def login_prompt(
    *, crm_login: str, ip_address: str | None, user_agent: str, expires_at: datetime
) -> str:
    lines = [
        "Вход в CRM",
        "",
        f"Учётная запись: {crm_login}",
        f"Адрес: {ip_address or 'неизвестен'}",
    ]
    if user_agent:
        lines.append(f"Браузер: {user_agent}")
    lines += [
        "",
        f"Запрос действует 3 минуты, до {expires_at:%H:%M:%S} UTC.",
        "Если это не вы, нажмите «Отклонить».",
    ]
    return "\n".join(lines)
