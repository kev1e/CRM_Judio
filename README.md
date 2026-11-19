# Корпоративная CRM

Внутренняя CRM одной компании: задачи и стандартизированные заявки, персональные доски, Telegram-бот. Спецификация — v1.3 (папка `docs/`).

**Состояние:** завершён технический фундамент (спринт S0). Бизнес-функций пока нет: есть каркас монорепозитория, служебные эндпоинты API, воркер, страница-заглушка, тесты, Docker Compose и CI. Следующие спринты — в `docs/ROADMAP.md`.

## Стек

| Часть                | Технологии                                                                  |
| -------------------- | --------------------------------------------------------------------------- |
| `apps/web`           | Next.js, React, TypeScript, Tailwind CSS, next-intl                         |
| `apps/api`           | Python, Django, Django REST Framework, Django ORM, PostgreSQL               |
| `apps/worker`        | Celery, Redis                                                               |
| `packages/contracts` | Схема OpenAPI из API и сгенерированные TypeScript-типы                      |
| `packages/config`    | Общие настройки TypeScript и ESLint                                         |
| `e2e`                | Playwright                                                                  |
| Инструменты          | pnpm, Turborepo, uv, Vitest + React Testing Library, pytest + pytest-django |

Точные версии и обоснование исключений — в `docs/ARCHITECTURE.md`.

## Быстрый запуск в Docker

Нужны только Docker и Docker Compose.

```bash
sh scripts/init-env.sh
```

```bash
docker compose up --build --wait
```

Первая команда создаёт `.env` со случайными локальными секретами (файл не попадает в Git). Вторая собирает образы, применяет миграции и ждёт, пока все сервисы станут healthy.

- Страница: http://127.0.0.1:3000
- API: http://127.0.0.1:8000/api/v1/ready

Проверка работающего стека (API, страница, задача через воркер):

```bash
sh scripts/smoke.sh
```

Остановка с удалением данных:

```bash
docker compose down --volumes
```

Без `scripts/init-env.sh` можно скопировать `.env.example` в `.env` и заменить все значения `change-me-...` вручную. С незаменённым секретом API намеренно не запускается.

## Разработка на своей машине

Требуются Node.js 26.13.1 (`.node-version`), pnpm 12.20.0, uv 0.13.7 и Docker. Python 3.14.10 uv установит сам по `.python-version`.

```bash
sh scripts/init-env.sh
```

```bash
pnpm install --frozen-lockfile
```

```bash
uv sync --locked --all-packages
```

PostgreSQL и Redis в Docker, с портами на localhost:

```bash
docker compose -f compose.yaml -f compose.dev.yaml up -d --wait postgres redis
```

```bash
pnpm --filter @crm/api run migrate
```

Затем в трёх терминалах:

```bash
pnpm --filter @crm/api run dev
```

```bash
pnpm --filter @crm/worker run dev
```

```bash
pnpm --filter @crm/web run dev
```

## Проверки

| Команда                | Что делает                                                                             |
| ---------------------- | -------------------------------------------------------------------------------------- |
| `pnpm lint`            | ESLint для TypeScript, Ruff для Python                                                 |
| `pnpm typecheck`       | `tsc` и mypy                                                                           |
| `pnpm test`            | Vitest (web), pytest (api и worker). Тестам Python нужны запущенные PostgreSQL и Redis |
| `pnpm build`           | Сборка Next.js                                                                         |
| `pnpm format:check`    | Prettier и `ruff format --check`                                                       |
| `pnpm contracts:check` | Схема OpenAPI и TypeScript-типы соответствуют коду API                                 |
| `pnpm e2e`             | Playwright против запущенного `docker compose up`                                      |

Перед первым запуском `pnpm e2e` установите браузер:

```bash
pnpm --filter @crm/e2e exec playwright install chromium
```

Те же проверки выполняет GitHub Actions (`.github/workflows/ci.yml`) на каждый push в любую ветку: frontend, backend, E2E, безопасность и дополнительный информационный прогон backend на Python 3.15.2.

## Изменение API и схемы данных

- После изменения эндпоинтов: `pnpm contracts:export`, затем `pnpm contracts:generate`, и закоммитьте `packages/contracts`.
- После изменения моделей: `uv run python manage.py makemigrations` в `apps/api`, закоммитьте миграцию. Применённые миграции не редактируются. Правила — в `docs/DATABASE.md`.

## Зависимости

- Версии закреплены точно; lockfile'ы — `pnpm-lock.yaml` и `uv.lock`.
- Новый релиз можно установить только через 7 дней после публикации (настроено в `pnpm-workspace.yaml` и `pyproject.toml`). Исключение для срочного исправления безопасности оформляется там же с комментарием — порядок в `docs/ARCHITECTURE.md`.

## Секреты

- `.env` и любые реальные учётные данные в репозиторий не попадают; в `.env.example` только заглушки.
- CI использует собственные тестовые значения, не имеющие силы за пределами прогона.

## Сброс и откат

- Сброс локальных данных: `docker compose down --volumes`, затем `docker compose up --build --wait`.
- Откат изменения: `git revert <коммит>`; каждая задача S0 оформлена отдельным коммитом.

## Документы

- `CLAUDE.md` — обязательные инструкции для Claude Code.
- `docs/PRD.md` — продукт и бизнес-требования.
- `docs/DECISIONS.md` — журнал решений (включая ожидающее решение D032).
- `docs/OPEN_QUESTIONS.md` — нерешённые вопросы; `BLOCKER` закрываются до соответствующего спринта.
- `docs/PERMISSIONS.md`, `docs/SECURITY.md`, `docs/TELEGRAM.md` — политики доступа, безопасности и Telegram.
- `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/INFRASTRUCTURE.md` — архитектура, данные, инфраструктура.
- `docs/UX_GUIDELINES.md`, `docs/ANALYTICS_AUTOMATIONS.md`, `docs/TEST_PLAN.md`, `docs/ROADMAP.md`.
- `prompts/` — промпты для запуска спринтов.

## Приоритет источников

1. Явно согласованные продуктовые решения в `docs/PRD.md` и `docs/DECISIONS.md`.
2. Подробные политики в `docs/PERMISSIONS.md`, `docs/SECURITY.md`, `docs/TELEGRAM.md`.
3. Архитектурные предложения в остальных документах, пока они не конфликтуют с требованиями.
4. При противоречии или пробеле бизнес-политика не придумывается: вопрос регистрируется в `docs/OPEN_QUESTIONS.md` и ждёт решения.

Открытые вопросы не считаются утверждёнными: объём файлов, RPO/RTO, авторизация при потере Telegram, часть политик удаления и архивирования и другие.
