# Telegram bot, Mini App, notifications and login confirmation

## Approved behavior

- Only **authorized active employees** with verified Telegram account link can create request tasks through bot, in private or authorized company group contexts.
- Provide both wizard (step-by-step conversation with bot) and Mini App (form using same published template validation).
- In a Telegram group, use an explicit bot command/deep link to start form. Avoid displaying sensitive fields publicly; prefer private chat or Mini App for data entry. Do not mirror chat messages or attach conversations to task.
- A request is a task with source provenance; choosing a specific eligible assignee is required and leads to immediate assignment, without managerial approval.
- Notifications to employee's personal bot dialog for assignment, due, mentions/comments, status, checkpoints, project invitations/approvals and scheduled digests. Notification routing must enforce ACL at send time.
- Login: Telegram username label + password; bot sends per-attempt approval (approve/deny), bound to stable `telegram_user_id`, not to mutable handle. Email verified as recovery contact, **admin-mediated** recovery/rebinding on Telegram loss.

## Implementation stack (revised 2026-11-19)

- Bot built with **aiogram** as its own process (`apps/telegram-bot`), sharing the Django code base: handlers call the same domain services as the web API and never write rows directly. Django ORM calls from async handlers go through the ORM's async interface or a thread executor, never blocking the event loop.
- Production uses webhook mode with the Telegram secret token header verified; long polling only in local development.
- Wizard state is kept in an aiogram FSM storage backed by Redis, keyed by Telegram user and chat, with a TTL.
- Mini App `initData` is validated on the server (signature and age) before any CRM data is returned; the Mini App then calls the same DRF endpoints as the website.
- Outbound notifications are sent by Celery tasks through the Bot API, using the outbox and permission re-check described below.

## Proposed secure account linking

1. Authenticated CRM user starts link flow or admin initiates supervised enrollment.
2. CRM generates short-lived single-use link token; employee opens bot, proves control of Telegram account.
3. Telegram service records verified numeric Telegram user ID, current username as display/login alias, and binding audit.
4. Reject duplicate bindings, expired/replayed tokens, unauthorized group messages. Username change must be supported without account takeover.

## Login MFA flow

1. User submits username/password over HTTPS; generic error responses and rate limiting, credentials hashed securely.
2. API creates short-lived login challenge with device details, random nonce, expiration and maximum attempts.
3. Bot sends approval request via personal DM to verified Telegram user ID; if bot cannot DM, fail safely and explain enrollment requirement.
4. User approves/denies within Telegram; backend correlates exact challenge and atomically consumes it.
5. API issues secure session (cookie flags/token policies), logs outcome; approval for another request cannot be reused.
6. During Telegram outage, **new Telegram-dependent login is blocked**. Existing valid web sessions continue while permissions remain current. Lost Telegram recovery is administrator-controlled, with extra identity proof and audit (details pending security review).

## Requests through Telegram

- For bot wizard: store ephemeral conversation state by Telegram user and flow session (NOT group-wide), track step + template_version + validation errors + idempotency token.
- For Mini App: validate Telegram signed initData server-side, check age, signature and active CRM linking; never trust fields from client, including assignee, department, price or file references.
- Validate requested template version is published and enabled for user's department/roles; validate relationship field targets via same resource ACL.
- Request creation service handles transaction, task status, checkpoints and outbox event; response returns task ID/reference but no unauthorized data.
- Telegram chat/message metadata stored only where needed for provenance/replay prevention; **no chat transcripts, no CRM chat UI, no unrestricted group history**.

## Webhook/queue reliability

- HTTPS endpoint, verify configured secret token and ingress restrictions. Deduplicate provider updates using unique `update_id`; acknowledge quickly, perform expensive operations asynchronously where safe.
- Store bot tokens in secret env/manager; restrict log redaction and permissions.
- Outbound delivery: idempotent jobs, retries with exponential backoff, honor provider rate limits and permanent failures; avoid leaking task details to users who lost access before send.
- Notification failure is logged/monitored; bot unavailable blocks inherently bot-dependent actions, **not** unrelated CRM features.

## Telegram limitations / open decisions

- Bot cannot automatically read arbitrary personal chats or old group history; this functionality is **not requested**.
- Bot direct notifications generally require users to have started or otherwise authorized private bot communication; onboarding flow must ensure this.
- In groups privacy mode/admin privileges affect which commands bot can see; use targeted commands or Mini App launches.
- Define which source groups are authorized, moderation/spam rules, recovery verification, outage behavior of pending login, exact formats of notification texts, scheduling preferences.
