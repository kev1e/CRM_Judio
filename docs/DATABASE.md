# Database — conceptual schema (PostgreSQL / Django ORM)

This is a **logical design**, not an approved concrete migration. Final names/cardinality, deletion constraints and indexing need schema review before code. Tables are implemented as Django models grouped by Django app (module); the table names below are conceptual.

## Django ORM and migration policy

- Schema changes only through Django migrations committed to the repository. CI fails when `makemigrations --check` reports model changes without a migration, and applies all migrations to an empty PostgreSQL database.
- Applied migrations are never edited; a fix is a new migration. Squashing only by a reviewed, separate change.
- Destructive or long-locking changes follow expand/contract over two releases and need explicit review. Data migrations are written to be re-runnable and are tested.
- Constraints live in the database, not only in Python: `UniqueConstraint` (including conditional ones), `CheckConstraint`, foreign keys with explicit `on_delete` (`PROTECT` by default for history-bearing rows, never an implicit `CASCADE`).
- **User model (D032 A1, approved):** the CRM user is an own model set as `AUTH_USER_MODEL` by the first identity migration. `django.contrib.auth`, `admin`, `sessions` and `contenttypes` are not installed, so their tables do not exist; sessions, roles and grants are own tables (D032 C1).
- Multi-step business operations use `transaction.atomic` with `select_for_update` where rows race; optimistic locking uses `row_version`.
- ID generation remains an open item (see the end of this document). PostgreSQL 18 provides `uuidv7()` natively, which makes time-ordered UUID primary keys available without extensions; this is a proposal, not a decision.

## Identity, organization and permissions

| Table | Primary fields / concepts |
|---|---|
| users | id UUID, display_name, email (verified), telegram_user_id (unique once linked), telegram_username (mutable), crm_login (unique, required), password_hash, active, created_at, deactivated_at |
| user_credentials | password lifecycle, rotations if policy requires |
| user_sessions | session_id, user_id, token hash, permissions_version, expiry, revoked_at |
| login_challenges | id, user_id, short expiry, pending/approved/denied/expired, device metadata, attempt nonce |
| departments | id, name, active, created_at |
| department_memberships | user_id, department_id, start/end; `is_primary` required for exactly one membership for each active employee; admin-controlled and audited |
| department_managers | department_id, manager_user_id, designated_for_handoff boolean (one active designated per dept), effective dates, active |
| roles | id, name, flags (avoid superuser=admin conflation) |
| permissions | code, action description, scope types |
| role_permissions | role_id, permission_id, scope |
| user_roles | user_id, role_id, optional organization scope, expiry |
| permission_versions | user_id, current_version, updated_at (or users.permissions_version) |

Indexes: unique email normalized as applicable; unique telegram_user_id, unique membership active constraint, efficient manager scope lookup. Do not store password or 2FA token plaintext.

## Project invitations

| Table | Fields / concepts |
|---|---|
| projects | id, name, owning_department_id (if applicable), active |
| project_members | project_id, user_id, role, joined_at, added_by |
| project_invitations | project_id, user_id, source_department_id, approving_department_id, requested_by, decided_by, state, timestamps, reason |

Invitation must not create membership until approval. Multi-department approving department explicit; approval action is atomic and audited.

## Tasks, requests, checkpoints

| Table | Fields / concepts |
|---|---|
| tasks | id, type_id, title, description, responsible_department_id NOT NULL, project_id nullable, author_id, status_id, priority, due_at nullable, completed_at nullable, archived_at nullable, deleted_at nullable, deleted_by nullable, row_version, created_at, updated_at |
| task_assignees | task_id, user_id, assigned_at, assigned_by; **v1 exactly one assignee per task (unique task_id); schema may evolve later** |
| task_types | id, key, label, default_template_id nullable, active |
| status_workflows | id, name, department_id/project_id scope TBD, default flag |
| task_statuses | id, workflow_id, label, position, category (new/active/completed/cancelled), color, active |
| allowed_status_transitions | workflow_id, from_status_id, to_status_id, optional permission policy |
| task_checkpoints | id, task_id, label, position, is_done, done_by, done_at, template_checkpoint_id nullable |
| task_comments | id, task_id, author_id, body, created_at, edited_at, deleted_at |
| attachments | id, task_id, uploader_id, storage_provider, object_key, original_name, byte_size, mime, sha256, created_at, deleted_at |
| task_events | append-only domain history (status, due_at, assignment, checkpoint etc.) |

The archive must not be a second copied task table. A completed task archived automatically remains searchable in Archive (subject to access). Trash uses `deleted_at` independent of archive; reopen: authorized manager/superuser to previous valid non-completed status, audited; manual archive may include incomplete tasks; Trash indefinite until administrator-authorized purge.

## Dynamic forms

| Table | Fields / concepts |
|---|---|
| form_templates | id, display_name, department_id, active, latest_published_version_id |
| template_versions | id, template_id, version, schema_json, published_at, published_by, immutable |
| template_fields | optional normalized indexed field definitions for analytics/filtering |
| task_form_submissions | task_id, template_version_id, values_json, schema_version |

Validate submitted `values_json` against **published** schema, including field types, currency/date format and employee/related-record permissions. Historical tasks retain original template_version_id and values. Dynamic field filterability requires safe typed metadata and indexes (not SQL string concatenation).

## Notifications, analytics, automation, observability

| Table | Fields / concepts |
|---|---|
| notifications | recipient_id, type, task_id nullable, state, created_at, read_at |
| notification_deliveries | notification_id, channel, attempt_count, last_error_redacted, sent_at |
| automation_rules | id, event_type, configuration_json, enabled, created_by_admin |
| scheduled_reports | id, created_by, recipients_scope, schedule, timezone, enabled |
| saved_views | id, owner_user_id, visibility (personal/shared), department_scope nullable, allowed_filters_json |
| dashboards | id, owner, scope, layout_json, widgets_json, created_at |
| audit_events | id, actor_user_id/service_actor, action, entity_type, entity_id, timestamp, safe old/new metadata, correlation_id |
| outbox_events | id, topic, version, payload, created_at, delivered_at, attempt_count |
| processed_external_events | provider, event_id (Telegram update_id), processed_at, unique(provider,event_id) |
| webhook_subscriptions | if needed; no group-message persistence |

## Data guarantees

- DB constraints: FK, not-null for responsible dept, uniqueness for telegram ID, safe deletion semantics, task/template relationship.
- Atomic operations for `complete + archive`, status transitions, deactivation + reassign, approval + membership, change rights + revoke version.
- Indexes for `task_assignees(user_id, task_id)`, `tasks(responsible_department_id, status_id, deleted_at, archived_at)`, `tasks(due_at)`, audit `(entity_type, entity_id, timestamp)`, lookup scope and template_version.
- Strict pagination, avoid N+1 access patterns. Audit metadata must not include raw passwords, 2FA challenge or sensitive secret values.
- Backups include DB plus file objects and relevant encryption keys/config, but keys backed up securely separately.

## To decide before migration generation

Task workflow scoping, file retention vs object backups, relation field targets, ID generation, migration strategy, approval exceptions and audit retention (Q14). Q01–Q09 and Q30 have been approved.

## Q05–Q09 data integrity and audit constraints

- Preserve `previous_noncompleted_status_id` or derive it from immutable, ordered status event history; never reopen to a completed/cancelled or inactive status implicitly.
- Introduce `archive_reason` (`automatic_completion` / `manual`) and `archived_by_id` (nullable for system action); keep `completed_at` unchanged for manual archival of unfinished tasks.
- For Trash, persist `deleted_at`, `deleted_by`, `restored_at` events; do not schedule automatic purge. Permanent purge must be explicit admin operation with impact review for attachments, references and retention.
- Designated handoff target and fallback must be validated as active and authorized. Transactionally lock departing assignee and impacted tasks, update assignee, revoke access and emit audit/outbox; block if no target.
- Status remapping should use explicit old-to-new IDs, save old labels/categories in audit, reject unsafe mapping, and transactionally migrate affected tasks; require admin confirmation.
- Transactional constraints: unique active primary membership per user; exactly one assignee per task in v1; designated handoff manager per department; index `deleted_at`, `archived_at`, status and responsible dept for scoped archive/trash.

## Q10–Q12 implementation additions (approved)

- `project_invitations.approving_department_id` denotes **explicitly selected participation department** of invited employee and must reference an active membership at decision time; validate approver's managed department or specific superuser approval permission. Record approver and history.
- Store short-lived one-use Telegram enrollment tokens as hashes only, with account ID, expiry, used timestamp and audit; bind `telegram_user_id` uniquely and transactionally. Avoid recording raw tokens in application logs.
- Track Telegram binding lifecycle (bound/revoked/rebound), admin actor and reason; revoke outstanding MFA approvals upon loss/recovery. Concrete identity-check procedure is still open.

## Approved Q13–Q14 database implications

- `users`: enforce a minimum-password policy at service boundary; only password hashes ever persisted. Store permission version for instant role/scope revocation.
- `login_challenges`: bind user, session attempt nonce, Telegram User ID, challenge state, `expires_at` = creation + 180 seconds, `consumed_at`, failed attempts and relevant safe metadata; add indexes to expire/reject pending challenges. Do not store a valid approval secret in plaintext.
- `user_sessions`: `created_at`, absolute `expires_at` (no more than 12 hours), `revoked_at`, permission version; enforce expiry on every authenticated API request.
- `auth_attempts` / throttling: minimal attempt counters and timestamps for progressive limits, privacy-aware retention, keyed by user and source; avoid logging raw passwords or OTPs.
- `audit_events`: add responsible department scope (or defensible historical scope snapshot) where applicable, actor, action, entity, safe diffs, time, correlation ID and classification/redaction metadata. Audit read requires scoped access; do not assume current task owner is always the appropriate scope for historical events.
- **No automatic audit purge**. Administrative cleanup must be explicit and independently recorded, subject to legal holds and retention checks. Plan indexes/partitioning for indefinite growth and separate immutable administrative cleanup records where needed.
- Q13/Q14 are approved policy requirements, not an instruction to generate migrations without review.


## Q15–Q16 — storage and recovery implications (approved)

- Keep file metadata and ACL linkage in PostgreSQL; attachment bytes stored on **local private persistent VPS volume**. Use a storage abstraction for portability but do not silently enable S3 as the primary store. Retain checksum, canonical storage key, original filename, validated file category, MIME signature, byte size ≤104857600, uploader, timestamps and deletion state.
- Supported categories: documents (PDF/Word/Excel), images, ZIP archives. Exact extension/content signature allowlist needs technical security review; reject unapproved formats. Do not automatically extract ZIPs.
- DB PITR-compatible recovery plus coordinated encrypted off-VPS snapshots of attachment bytes must target **RPO ≤1h** and **RTO ≤4h**, with **30-day** backup retention. DB and attachment backups must have a documented consistent recovery point (file upload transaction state, pending objects and orphan cleanup).
- Capacity planning thresholds, actual storage consumption, disk sizing, offsite backup provider and key management remain open implementation details; do not claim disaster recovery compliance until demonstrated by restore tests.

## Approved Q17–Q18 database implications

- `tasks`: retain an immutable original deadline baseline (including explicit nullable-original semantics), current due date, and timestamped audit events for every due-date edit. Completed/cancelled and archive semantics remain distinct.
- Add a durable history/event or normalized cycle structure recording `task_id`, cycle number, executor at assignment, assignment start time, completion time, reopen time, effective due date on completion, and status change references. Preserve history across reassignment and reopening.
- Each actual completion transition and its automatic archive must be atomic. Reopen and subsequent completion must **not** overwrite the historical completion/cycle row.
- Add indexes for scoped time-window aggregates, status/category, responsible department and task assignment/cycle data. Analytics access remains governed by the existing record-level ACL.
- The *precise* schema for reassignment and cycle start/stop is not approved here and must not be silently inferred.

## Q19 — Data and audit implications

- Task status transitions: transactional status history with actor, previous/current status, reason if required by transition rule; completing and automatic archival in one transaction.
- Checkpoint events track creator/updater and completion/uncompletion actor/timestamps. Avoid granting update permission from mere task visibility.
- Comment revision history must be append-only or versioned (comment ID, editor, edited_at, revision, safe old/new text); original comment ownership remains stable, and historical edits remain audit-access-controlled.
- Attachment metadata records actor, owning task, scoped file ACL and audit event for upload/delete. Binary blobs remain in approved local VPS storage, not audit records.
- Priority changes and deadline changes must preserve prior/current values with event times. Deadline audit must support previously approved Q17 original/current metrics.
- Enforce single assignee as approved Q03; only permitted manager/superuser reassignment. Application-level authorization and database transactions both required.

## Q20–Q21 approved logical data changes

- `saved_views`: `id`, `owner_user_id`, `visibility` (`personal`/`department`/`company`), `filter_definition` (validated/allowlisted JSON), timestamps, audit fields. For department scope, use explicit `saved_view_departments(saved_view_id, department_id)` or equivalent scope relationship; constrain publisher to management of every selected department. Personal views must have no shared scope; publishing must not bypass record ACL.
- `form_templates`: administrator-owned metadata and state; add a normalized `template_allowed_departments(template_id, department_id)` relationship or equivalent, with explicit deny-by-default availability and indexes. New immutable `template_versions` are created for each publication; old submissions continue referencing their original version.
- Query-time permissions: department membership and manager assignments may change, so saved view readers and request template eligibility must be determined from current backend state, never cached as static read permissions. All create/publish/retire/allowlist changes have auditable actor and timestamps.
- Treat these as logical requirements, not an authorization to execute migrations without schema review. The older `saved_views.visibility (personal/shared)` model is superseded by Q20's three explicit visibility scopes. Existing `form_templates.department_id` alone is not sufficient if a template may target several explicitly designated departments.

## Q28–Q29 — Approved schema implications (conceptual, migrations not yet approved)
- Email verification needs auditable fields or events: normalized recovery email, `email_verified_at`, `email_verified_by_admin_id`, verification history/invalidation and actor/timestamp of change. `email_verified` must never be set from employee-provided data alone. Invalidate old verification after address changes; do not store unneeded identity-proof payloads.
- Model administrator-mediated recovery requests/status and append-only security/audit events (who requested, authorized administrator, checks completed, revoked sessions/bindings/challenges, outcome). Exact identity evidence schema and retention are OPEN.
- Keep **administrator** identity/role distinct from **superuser** company-task-read access. Express operations through explicit permission/action grants and appropriate scopes, with permission version invalidation; `is_superuser` must not become a shortcut in the business authorization service.
- Maintain denial for unauthorized writes even when user has global task READ access; migration/schema for grants should support `task.read`, `task.update`, `task.assign`, `task.archive`, `task.restore`, `project.invitation.approve`, etc., without silently approving additional rights.

## REC-01 / REC-02 recovery data requirements
- Model a `recovery_request` or equivalent append-only audit-linked workflow: target user, initiating actor, assigned administrator, linked existing manager ID, minimal HR-identity check outcome (boolean/status, **not copied sensitive HR details**), manager confirmation status/timestamp, outcome, reason code, and security action references.
- Recovery approval and reset must use atomic state transitions; prevent reuse/duplicate approval and race conditions. Revoke old Telegram bindings/MFA challenges/sessions and issue new one-time binding tokens with Q11/Q13 semantics.
- Mark the emergency administrator account as explicitly distinguished for monitoring and restricted workflows; never store emergency secrets in DB cleartext or source code. Record every break-glass session and action with tamper-resistant audit/alert references.
- Exact HR fields, confirmation channel, fallback, break-glass authentication and secret custody remain OPEN; schema choices must not silently set policy.

## Implemented schema

Concrete tables created by migrations so far. Everything above remains the logical design for the parts not built yet.

### S1.1 — identity, RBAC core, audit

| Table | Columns | Constraints |
|---|---|---|
| `identity_user` | `id` UUIDv7, `crm_login`, `display_name`, `password` (Argon2id hash), `last_login`, `email`, `email_verified_at`, `email_verified_by_id`, `telegram_user_id`, `telegram_username`, `telegram_bound_at`, `is_active`, `deactivated_at`, `permissions_version`, `created_at`, `updated_at` | `crm_login` unique and format-checked; `telegram_user_id` unique when set; `email` unique when set and lowercase; verified state requires both the address and the verifying administrator; Telegram ID and binding time are set together; inactive ⇔ `deactivated_at` set |
| `access_role` | `id`, `key`, `name`, `description`, `is_system`, `created_at` | `key` unique and format-checked |
| `access_role_grant` | `id`, `role_id`, `permission_code`, `scope` | one row per (role, permission); `scope` ∈ `own`, `managed_departments`, `company` |
| `access_user_role` | `id`, `user_id`, `role_id`, `granted_at`, `granted_by_id` | one row per (user, role); users and roles are protected from deletion while linked |
| `audit_event` | `id` UUIDv7, `occurred_at` (database clock), `actor_type` (`user`/`system`/`cli`), `actor_id`, `actor_label`, `action`, `entity_type`, `entity_id`, `metadata` JSON, `correlation_id` | a `user` actor must reference a user and other actors must not; trigger `audit_event_append_only` refuses every UPDATE, and every DELETE outside a transaction that set `crm.audit_cleanup = 'on'` |

Notes:

- The permission catalogue lives in code (`crm/access/permissions.py`), not in a table: a permission only exists together with the code that checks it. `access_role_grant.permission_code` is validated against the catalogue by the service.
- The built-in `administrator` role is created by a data migration; its grants change only through migrations.
- `permissions_version` is incremented in the same transaction as any change of the user's roles or of the grants of a role they hold.
- The audit row has no department scope column yet; it is added with departments in S2 (Q14 scoped reading).
- Not built yet: sessions, login challenges, enrollment tokens, throttling counters, recovery requests, the emergency-account marker.
