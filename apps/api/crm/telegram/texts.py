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
    "который вам выдал администратор:\n/start КОД\n\n"
    "Руководителям: подать заявку по шаблону — /request"
)
ENROLLMENT_DONE = (
    "Готово: Telegram привязан к учётной записи CRM. "
    "Сюда будут приходить запросы на подтверждение входа."
)
SETUP_LINK_NOT_AVAILABLE = (
    "Ссылку для установки пароля сейчас выдать нельзя. Она нужна только один раз — "
    "новой учётной записи без пароля. Если пароль утерян, обратитесь к администратору."
)
ENROLLMENT_REJECTED = (
    "Код привязки недействителен или его срок истёк. Попросите администратора выдать новый код."
)

LOGIN_APPROVED = "Вход подтверждён. Вернитесь на страницу CRM."
LOGIN_DENIED = "Вход отклонён. Если вы не пытались войти, смените пароль и сообщите администратору."
LOGIN_NOT_VALID = "Запрос на вход уже недействителен или его срок истёк."
TEMPORARY_FAILURE = "Не удалось выполнить действие. Попробуйте ещё раз."


BUTTON_OPEN_SETUP = "Задать пароль"


def password_link(*, url: str, expires_at: datetime, as_button: bool) -> str:
    """`as_button`: the link is attached as a button, so the address is not repeated
    in the text. Otherwise the address itself is written out."""
    lines = ["Осталось задать пароль для входа в CRM."]
    if as_button:
        lines.append("Нажмите кнопку под этим сообщением и придумайте пароль.")
    else:
        lines += ["Откройте ссылку и придумайте пароль:", url]
    lines += [
        "",
        f"Ссылка одноразовая и действует до {expires_at:%H:%M} UTC. "
        "Никому её не пересылайте. Если срок истёк, отправьте /password.",
    ]
    return "\n".join(lines)


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


BUTTON_OPEN_TASK = "Открыть в CRM"


def _quoted(title: str) -> str:
    return f"«{title}»"


def task_assigned(
    *, title: str, is_request: bool, department: str, due: str | None, actor: str | None
) -> str:
    lines = [
        f"Вам назначена {'заявка' if is_request else 'задача'} {_quoted(title)}.",
        "",
        f"Отдел: {department}",
        f"Срок: {due or 'не указан'}",
    ]
    if actor:
        lines.append(f"Назначил(а): {actor}")
    return "\n".join(lines)


def deadline_changed(*, title: str, due: str | None, actor: str | None) -> str:
    who = f"{actor} изменил(а)" if actor else "Изменён"
    return f"{who} срок задачи {_quoted(title)}.\n\nНовый срок: {due or 'без срока'}"


def comment_added(*, title: str, actor: str | None) -> str:
    who = f" от {actor}" if actor else ""
    return f"Новый комментарий{who} к задаче {_quoted(title)}."


# --- The request dialogue (S6) ----------------------------------------------

REQUEST_NOT_LINKED = (
    "Заявку может подать только сотрудник с привязанной учётной записью CRM. "
    "Если вы сотрудник, обратитесь к администратору."
)
REQUEST_NO_FORMS = (
    "Нет шаблонов, по которым вы можете подать заявку. "
    "Шаблоны и отделы, которым они доступны, настраивает администратор."
)
REQUEST_CHOOSE_FORM = "Новая заявка. Выберите шаблон:"
REQUEST_CHOOSE_DEPARTMENT = "Для какого отдела заявка?"
REQUEST_CHOOSE_ASSIGNEE = "Кто исполнитель?"
REQUEST_NO_ASSIGNEES = "В этом отделе нет сотрудников, которым можно назначить заявку."
REQUEST_USE_BUTTONS = "Выберите вариант кнопкой под сообщением. Отменить заявку: /cancel"
REQUEST_TYPE_TEXT = "Отправьте ответ текстом. Отменить заявку: /cancel"
REQUEST_SEND_FILE = "Отправьте файл (документом или фото). Отменить заявку: /cancel"
REQUEST_STALE = "Эта кнопка уже неактуальна."
REQUEST_CANCELLED = "Заявка отменена. Ничего не создано."
REQUEST_NOTHING_TO_CANCEL = "Сейчас нет заявки, которую можно отменить."
REQUEST_EXPIRED = "Заполнение заявки прервано. Начните заново: /request"
REQUEST_TEMPLATE_CHANGED = (
    "Шаблон изменился или стал недоступен, пока вы заполняли заявку. Начните заново: /request"
)
REQUEST_REFUSED = "Заявку не удалось создать. Начните заново: /request"
REQUEST_FILE_TOO_LARGE = (
    "Через Telegram можно отправить файл до 20 МБ. Файл больше приложите в CRM."
)
REQUEST_FILE_REFUSED = (
    "Этот файл нельзя приложить. Допустимы PDF, Word, Excel, изображения и ZIP. "
    "Отправьте другой файл."
)
REQUEST_FILE_FAILED = "Не удалось получить файл. Отправьте его ещё раз."

BUTTON_SKIP = "Пропустить"
BUTTON_DONE = "Готово"
BUTTON_YES = "Да"
BUTTON_NO = "Нет"
BUTTON_SUBMIT = "Подать заявку"
BUTTON_CANCEL = "Отмена"

_REASONS = {
    "required": "это поле обязательно.",
    "invalid": "значение указано неверно.",
    "too_long": "слишком длинный текст.",
    "out_of_range": "значение вне допустимых границ.",
    "too_precise": "слишком много знаков после запятой.",
    "not_integer": "нужно целое число.",
    "not_an_option": "выберите значение из предложенных.",
}


def request_title(*, default: str) -> str:
    return f"Название заявки? Отправьте его текстом или оставьте «{default}»."


def button_keep_title(default: str) -> str:
    return f"Оставить «{default[:40]}»"


def request_refusal(reason: str) -> str:
    return f"Не подходит: {_REASONS.get(reason, _REASONS['invalid'])} Попробуйте ещё раз."


def request_question(
    *,
    label: str,
    kind: str,
    required: bool,
    hint: str,
    currency: str | None,
    with_time: bool,
    multiple: bool,
    number: int,
    total: int,
) -> str:
    lines = [f"{number} из {total}. {label}" + ("" if required else " (необязательно)")]
    if hint:
        lines.append(hint)
    if kind == "number":
        lines.append(f"Введите число{', ' + currency if currency else ''}.")
    elif kind == "date":
        lines.append(
            "Введите дату и время, например 15.12.2026 14:30."
            if with_time
            else "Введите дату, например 15.12.2026."
        )
    elif kind == "select":
        lines.append(
            "Отметьте нужные варианты и нажмите «Готово»." if multiple else "Выберите вариант."
        )
    elif kind == "employee":
        lines.append("Выберите сотрудника.")
    elif kind == "file":
        lines.append("Отправьте файл документом или фото, до 20 МБ.")
    elif kind == "boolean":
        lines.append("Да или нет?")
    return "\n".join(lines)


def request_summary(
    *, form: str, title: str, department: str, assignee: str, answers: list[tuple[str, str]]
) -> str:
    lines = [
        "Проверьте заявку.",
        "",
        f"Шаблон: {form}",
        f"Название: {title}",
        f"Отдел: {department}",
        f"Исполнитель: {assignee}",
    ]
    if answers:
        lines.append("")
        lines += [f"{label}: {value}" for label, value in answers]
    return "\n".join(lines)


def request_created(*, title: str, assignee: str) -> str:
    return f"Заявка «{title}» создана и назначена: {assignee}."
