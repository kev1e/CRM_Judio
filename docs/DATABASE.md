# Database — conceptual schema (PostgreSQL / Django ORM)

This is a **logical design**, not an approved concrete migration. Final names/cardinality, deletion constraints and indexing need schema review before code. Tables are implemented as Django models grouped by Django app (module); the table names below are conceptual.

## Django ORM and migration policy

- Schema changes only through Django migrations committed to the repository. CI fails when `makemigrations --check` reports model changes without a migration, and applies all migrations to an empty PostgreSQL database.
- Applied migrations are never edited; a fix is a new migration. Squashing only by a reviewed, separate change.
- Destructive or long-locking changes follow expand/contract over two releases and need explicit review. Data migrations are written to be re-runnable and are tested.
- Constraints live in the database, not only in Python: `UniqueConstraint` (including conditional ones), `CheckConstraint`, foreign keys with explicit `on_delete` (`PROTECT` by default for history-bearing rows, never an implicit `CASCADE`).
- **User model (D032, pending):** Django requires the user model to be chosen before the first migration that references it. The S0 baseline therefore creates no `django.contrib.auth` tables and contains a single technical table, `system_heartbeat`. Whether `users` below becomes a custom Django user model, and whether roles/grants are own tables or Django groups/permissions, is decided in D032 before S1.
- Multi-step business operations use `transaction.atomic` with `select_for_update` where rows race; optimistic locking uses `row_version`.
- ID generation remains an open item (see the end of this document). PostgreSQL 18 provides `uuidv7()` natively, which makes time-ordered UUID primary keys available without extensions; this is a proposal, not a decision.

## Identity, organization and permissions

| Table | Primary fields / concepts |
|---|---|
| users | id UUID, display_name, email (verified), telegram_user_id (unique once linked), telegram_username (mutable), password_hash, active, created_at, deactivated_at |
| user_credentials | password lifecycle, rotations if policy requires |
| user_sessions | session_id, user_id, token hash, permissions_version, expiry, revoked_at |
| login_challenges | id, user_id, short expiry, pending/approved/denied/expired, device metadata, attempt nonce |
| departments | id, name, active, created_at |
| department_memberships | user_id, department_id, start/end; optional `is_primary` **requires product decision** |
| department_managers | department_id, manager_user_id, effective dates, active |
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
| task_assignees | task_id, user_id, assigned_at, assigned_by; **single vs multi-assignee OPEN** |
| task_types | id, key, label, default_template_id nullable, active |
| status_workflows | id, name, department_id/project_id scope TBD, default flag |
| task_statuses | id, workflow_id, label, position, category (new/active/completed), color, active |
| allowed_status_transitions | workflow_id, from_status_id, to_status_id, optional permission policy |
| task_checkpoints | id, task_id, label, position, is_done, done_by, done_at, template_checkpoint_id nullable |
| task_comments | id, task_id, author_id, body, created_at, edited_at, deleted_at |
| attachments | id, task_id, uploader_id, storage_provider, object_key, original_name, byte_size, mime, sha256, created_at, deleted_at |
| task_events | append-only domain history (status, due_at, assignment, checkpoint etc.) |

The archive must not be a second copied task table. A completed task archived automatically remains searchable in Archive (subject to access). Trash uses `deleted_at` independent of archive; restore/unarchive rules TBD.

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

Primary dept vs unlimited memberships, single/multiple assignees, task status workflow scoping, who can delete/recover, file retention, archive restore conditions, how custom relation fields reference future modules, ID generation and migration strategy, session mechanism for the custom user model (S1).
