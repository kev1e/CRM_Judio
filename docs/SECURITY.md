# Security specification — mandatory review and test targets

## Main threats

IDOR/record leakage, overbroad multi-department managers, creator bypass to unassigned tasks, manipulated Mini App requests, Telegram username reassignment, stolen Telegram account, brute-force password/MFA, replayed webhook, file URL leakage, CSV formula injection, template schema injection, privilege escalation by managers, stale caches/sessions, misconfigured backup/CI secrets.

## Requirements

- **Least privilege:** task read scope enforce on all endpoints, exports, search, widgets, downloads, websocket channels, worker queries. Existence of hidden records should not be revealed through error details.
- **Session & credentials:** robust password hash (e.g., Argon2id with reviewed parameters), strong reset/rebinding policies, HttpOnly/Secure/SameSite cookies where appropriate, session expiry/revocation, rate limiting, login CSRF/origin controls.
- **Telegram MFA:** exact challenge binding, short TTL, single use, no acceptance from username alone, secret/callback signature validation, replay protection, denial audit, secure account recovery via admin with identity proof.
- **Role changes:** immediate server enforcement, permission-version checks and invalidation of sessions/caches/live channels; test role removal while tab remains open.
- **Data validation:** JSON schema/published template only; field-level ACL; sanitize rich text/markdown, guard XSS/CSRF, prevent mass assignment; safe API query limits.
- **Files:** maximum 100 MB, upload authorization, server-side MIME/content checks, anti-malware strategy, object keys randomized, private buckets/volumes, download after authorization, short-lived signed URLs only when appropriate, retention and deletion lifecycle.
- **Export:** authorize rows and columns, prevent CSV/Excel formula injection, audit export actor/scope; limit report size.
- **Infrastructure:** public access only to proxy/TLS endpoints, DB/Redis private network, non-root containers, env secret protection, security updates, staging/prod separation, encrypted backups off-host, regular restore drills.
- **Logs and audit:** track changes to tasks, users, roles/grants, templates, config and privileged actions, with actor/time/context; redact secrets and sensitive descriptions, restrict audit access and establish retention policy.
- **Workers:** do not grant a worker arbitrary database read independent of application policy. Job payloads carry IDs, not whole sensitive records, and re-authorize on delivery.

## Safety-critical cases to test

1. Staff guessing other employees' task IDs or file URLs cannot retrieve content.
2. Author of a task assigned to someone else cannot bypass `assignee only` rule via author ownership.
3. Manager of department A cannot read B's tasks even when employee belongs to both.
4. Superuser with task-read right but without admin right cannot edit role grants.
5. Admin without superuser read right cannot browse all task bodies.
6. Manager cannot create a new admin/superuser role grant.
7. Permission revocation takes effect mid-session for list, detail, search, download, export, live updates.
8. Archived/deleted records obey the same or stricter ACL.
9. Web/Mini App/bot all reject field tampering or unauthorized assignee.
10. Telegram challenge cannot be replayed or approved from another Telegram ID.
11. Concurrent status update and archive cannot leave completed visible on active board without archive.
12. Backup recovery restores both DB and files and does not expose credentials.

## Policies not yet fixed

Password policy, session TTL, MFA challenge TTL, admin identity verification for Telegram recovery, incident response, audit retention, permanent deletion, RPO/RTO, compliance/locality requirements. Do not invent them silently; use interim secure development defaults only if explicitly labelled as provisional and not for production.
