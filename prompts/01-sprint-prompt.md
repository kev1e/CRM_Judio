# Reusable Claude Code sprint prompt

Implement only sprint `<SPRINT_ID>` / work item `<ISSUE_ID>` from `docs/ROADMAP.md`.

1. Read `CLAUDE.md`, `docs/PRD.md`, `docs/PERMISSIONS.md`, `docs/DECISIONS.md`, `docs/OPEN_QUESTIONS.md` and any feature-relevant documentation.
2. Report any unresolved BLOCKER before coding; do not silently decide product policy.
3. Produce a small implementation plan stating touched files, DB migration, ACL effect, API contract, UI steps, tests and deployment risk.
4. After plan approval: implement just this slice, with minimal cohesive diffs, secure defaults and explicit test fixtures.
5. Run lint, type checks, tests and relevant migration/CI commands; document exactly what passed or did not run.
6. Add **negative authorization tests** to any operation that reads or mutates records. Verify impersonation/bot/web boundaries as relevant.
7. Update docs and decision log when implementation clarifies but does not change approved behavior.
8. Summarize work in Russian: implemented, tests run, known risks, deployment notes, next tiny issue.

Never expand this issue into unrequested modules or secretly change the rule that an ordinary employee sees only assigned tasks. Do not auto-transition task status when checkpoints complete. Completion auto-archives; manual archive only for manager/superuser. Telegram chats are not mirrored into CRM.
