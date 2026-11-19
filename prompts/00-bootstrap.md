# First Claude Code prompt — repository bootstrap only

You are starting development of a new internal corporate CRM. Before writing any implementation code, read **all** repository documents: `CLAUDE.md`, `README.md` and the entire `docs/` directory. The approved product decisions are in `docs/PRD.md` and `docs/DECISIONS.md`; `docs/OPEN_QUESTIONS.md` is a mandatory risk log.

**Task for this turn:** prepare a technical readiness review and a small plan for Sprint S0 only. Do not implement the entire CRM and do not implement other sprints. Do not invent business rules.

Return, in Russian:
1. Summary of mandatory requirements and explicit non-goals.
2. Any conflicts/contradictions, marked BLOCKER or NON-BLOCKER, with doc references.
3. Proposed exact compatible dependencies and toolchain versions, backed by documentation/compatibility checks.
4. Proposed monorepo folder structure, architecture boundaries, Django migration policy, CI test gates and Docker local setup.
5. Ordered S0 implementation tasks with acceptance tests and a rollback/reset plan.
6. Minimal questions that MUST be resolved before S0; leave questions for later sprints in the existing open-question log.

Wait for approval of the S0 plan before altering project files. No passwords, bot tokens, customer data or production secrets in the repository.
