# ADR-0101 — The owner is a role; every other admin holds ticked permissions

**Status:** Accepted
**Date:** 2026-11-21

**Relates to:** ADR-0041 (an account's powers), #3258 (the hardcoded owner id), #3847, #3821

## Decision

- **Owner** is a row in `role`, held through `account_role`. The migration gives it to
  account 1; after that it is set only from `elevate_admin.py` or the DB, never an HTTP
  route. More than one account may hold it. Nobody checks an account id for ownership.
- **Admin** = owner, or at least one row in `account_permission`
  (`account_id`, `permission`, `granted_by_id`, `granted_at`; unique per pair). There is
  no separate admin flag, and the old `admin` role row was deleted by the migration.
  `dependencies.account_has_admin_role` is the one definition.
- The owner holds all nine permissions implicitly: `handle_reports`, `ban_suspend`,
  `review_proposals`, `manage_tasks`, `delete_import_tasks`, `read_messages`, `edit_copy`,
  `small_world`, `roll_era`. The set is a closed enum with a CHECK; a tenth is a revision.
- Every admin route declares one permission through `require_permission`; the overview and
  the mod log need only "is admin". `PUT /admin/tasks/{id}/status` spans three boxes and
  re-checks the finer one by transition (proposal, delete, everything else). A test fails
  on an admin route with no declaration.
- Only the owner grants permissions, through the roster.
- **Ban and suspend** refuse yourself and any owner account, for everyone; only the owner
  may target another admin. Unban and unsuspend are never guarded, so a bad past action
  can still be undone.
- **Score hand-editing is gone for everyone.** `PATCH /admin/characters/{id}/stats` wrote
  `score` without `all_time_score` and stuck `peak_level`. A wrong score is fixed by
  recalculation or by undoing its cause.
- Admins that existed before the migration, other than account 1, start with no boxes.
