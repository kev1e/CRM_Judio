# Open questions and decisions needed before production

**Rule:** An unanswered question is not implicit approval of the proposed default. Mark final choices as APPROVED in `DECISIONS.md` and update all affected specifications/tests.

## BLOCKER — before building the affected feature

| ID | Question | Current suggestion / why important |
|---|---|---|
| Q01 | How designate a **primary department** while allowing membership in any number? | Admin sets exactly one primary membership, can change with audit; needed for deactivation handoff |
| Q02 | If the creator assigns a task to someone else, may creator still access/edit it? | Existing mandatory rule employee sees only assigned task. Recommended: provide creation confirmation only; no later read unless separately assigned/manager/superuser |
| Q03 | Can one task have multiple assignees? | UI says “исполнитель” singular, but prior design considered task_assignees plural. Recommend one initial assignee; preserve extensible schema only if confirmed |
| Q04 | What specifically marks a task **completed**? | Admin-configurable status with `category=completed`; when first entering it, atomically auto-archive. Decide whether multiple completed statuses allowed |
| Q05 | Can archived tasks be reopened, and who may do so? | Avoid accidental unarchive by assignee; define exact status restoration rule and manager/superuser scopes |
| Q06 | Who can soft-delete and restore, who can permanently purge, for how long keep Trash? | Mechanism approved, authority/retention not agreed. Security-sensitive |
| Q07 | Manager/superuser **manual** archive and auto-archive interaction | Interpretation: automation by system, manual actions privileged. Confirm if manual archive before completion permitted |
| Q08 | How decide which manager receives deactivated employee's work if multiple managers for primary dept or the fallback superuser pool? | Define deterministic fallback/queue, lock concurrency, log decisions |
| Q09 | How are existing tasks migrated when admin edits/removes statuses/transitions? | Preserve history, prohibit deleting in-use status without explicit mapping |
| Q10 | When manager from another dept invites multi-dept employee, which department manager approves? | Explicit selection and validation to prevent bypass |
| Q11 | How can employees initially link Telegram ID before first Telegram-MFA login? | Secure enrollment + admin-assisted bootstrap + private bot initiation |
| Q12 | Telegram-loss recovery identity proof and emergency administrative account access | Admin-mediated reset, not email-only bypass; define strong identity checks and break-glass process |
| Q13 | Password, session and MFA challenge expiry/lockout rules | Need safe thresholds and approved recovery/2FA controls |
| Q14 | Which users can view audit events, and how long is audit retained? | Needed for sensitive employee and task information |
| Q15 | RPO/RTO and acceptable downtime; then backup cadence | User explicitly requested assessment first. Do not assume daily copies meet need |
| Q16 | File volume, types, virus scanning requirements, encryption and location -> storage provider | Max file 100MB, total volume unknown |
| Q30 | A Telegram account may have **no username**, and usernames change. What is the CRM login label then, must it be unique, and who updates it? (registered 2026-11-19, needed for S1) | Suggestion: CRM keeps its own unique login field, pre-filled from the Telegram username at binding and editable under audit; identity stays bound to Telegram ID. Not approved |

## Important before advanced modules

| ID | Question | Implication |
|---|---|---|
| Q17 | Is completion date due date current/original for on-time KPI? | Prevent deadline gaming and incorrect metrics |
| Q18 | Is average completion time calculated from creation or assignment; how handle reopened tasks? | KPI definition |
| Q19 | Which tasks can employee/author change: status, checkpoints, comments, priority, due date, attachments? | Field-level permissions; assignment edit is strictly manager/superuser |
| Q20 | Are shared views department-only, per-project, or user-shared? Who can publish? | Access never broader than viewer permission |
| Q21 | What kinds of request templates may employees use; who approves template publication? | Template availability and version controls |
| Q22 | Which groups may use the bot? How to handle group visibility and confidential form fields? | Private entry/Mini App best practice |
| Q23 | Scheduled digest recipient/timezone and retry/failure policies | Only approved flexible scheduling so far |
| Q24 | Should employee be able to access Archive directly; when should archive affect search and KPIs? | Define view settings and record retention |
| Q25 | Data location/compliance (personal data, employee records, cross-border Telegram use) | VPS jurisdiction, provider, GDPR where applicable |
| Q26 | Actual load/SLA expectations and deployment approval policy for production | Select VPS and thresholds empirically |
| Q27 | Full domain model of related CRM records (contacts, companies, deals, products) | Universal CRM is goal, but full business modules were not explicitly chosen; avoid inventing them in sprint 1 |
| Q28 | Email recovery contact verification, delivery provider and policy | User specified verified email for recovery, admin-controlled action |
| Q29 | Status of 'superuser' editing: company-wide read is approved, edit scope/approvals require separate specific grants | Avoid privilege escalation |

## Sprint mapping gaps noticed during the readiness review (2026-11-19)

- Q28 (recovery email verification) is needed for S1 although it is listed under advanced modules.
- Q29 (superuser edit scope) and Q14 (audit visibility/retention) are needed for S2.
- "Who may mark a task completed" is listed in `PERMISSIONS.md` as open but has no ID; treat it as part of Q19 before S3.
- A live-update transport (WebSocket/SSE) is implied by the revocation requirements but not chosen; decide before the first feature that pushes data to the browser.

## Proposed clarifying decisions to request early

Ask Q01–Q09 and Q11–Q16 in small logical batches, not one huge questionnaire. Prioritize user experience/security blockers before sprint concerned. Work on repo scaffolding, auth skeleton and documentation without silently answering business questions.
