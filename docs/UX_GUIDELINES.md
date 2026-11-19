# UX Guidelines — YouGile-inspired, not a clone

## Principle

Fast work with minimal buttons and navigation. Favor sensible defaults and progressive disclosure. Keep destructive actions explicit. Do not sacrifice security/accessibility to save clicks.

## Primary navigation

- Landing page: `Мои задачи` personal Kanban filtered by server ACL.
- Other navigation (if user permitted): department/projects, archive, reports, admin.
- Use contextual menus for secondary operations. Avoid popups-within-popups.
- Search: global entry plus local search; only authorized results.

## Board

- Admin owns status/column definitions; drag/drop allowed only if server validates transition.
- Personal board is a **view of canonical tasks**, not copied task records.
- Mini-card contains exactly: task name, priority, deadline, checkpoint progress, project OR department as applicable, assignee.
- Compact cards, whitespace, readable typographic hierarchy, states for overdue, empty, loading, offline and permission-denied. Keyboard alternative to drag/drop.
- Personal/shared saved filters, mobile list option if board columns cannot fit.

## Task modal

- Click card to open modal with deep-linkable URL, keyboard Escape/back support, focus trap, screen-reader title and logical tab navigation.
- Main fields visible first: name, status, assignee, priority, due date, project/department, description.
- Collapsible blocks: checkpoints, comments and attachments, history, template-specific details.
- Default read mode; explicit `Редактировать` toggles edit mode. Save and Cancel visible only while editing. Prevent accidental loss of unsaved changes.
- Editing available only within backend-enforced rights; assignee change control only manager/superuser. Display reason if unable to change status due to rule.
- Show upload progress for 100 MB max; file types/validation and secure download behavior.

## Archive, trash and states

- Completion immediately archives task (backend transaction) and removes from active board, with clear transient confirmation and link to Archive.
- Archive distinct from Trash. Archived task keeps completed status, audit and comment history.
- Restore from trash is policy-gated; never accidentally show deleted tasks in normal search.
- For admin changes to statuses/templates/roles, show preview/impact and explicit confirm for destructive changes.

## i18n & themes

- Russian default; all UI strings sourced from translation catalogs (not hard-coded in JSX); support future locales and locale-aware number/date/money/timezone formatting.
- Light and dark mode with persistent preference, accessible contrast.
- Responsive layout for browser; Mini App is a separately optimized form flow.

## Design review checklist

Does this screen require more clicks than necessary? Does it add a second navigation step for a routine action? Are privileges hidden in UI AND denied in API? Are controls keyboard accessible? Does error messaging explain next action? Are loading/empty states useful? Does mobile layout remain usable?
