import { useAuth } from './AuthContext'
// Type-only: TaskCard is eager, so this file must not reach api/admin at runtime (#1141).
import type { Permission } from '../api/admin'

/** Read off each route's `require_permission` in `backend/routers/admin.py`; any one opens it, `[]` is any admin. */
export const NEEDS = {
  reports: ['handle_reports'],
  praxis: ['handle_reports'],
  moderate: ['handle_reports'],
  messages: ['read_messages'],
  proposals: ['review_proposals'],
  tasks: ['manage_tasks', 'delete_import_tasks'],
  editTask: ['manage_tasks'],
  deleteTask: ['delete_import_tasks'],
  people: ['ban_suspend'],
  banSuspend: ['ban_suspend'],
  smallWorld: ['small_world'],
  era: ['roll_era'],
  copy: ['edit_copy'],
  modLog: [],
} as const satisfies Record<string, readonly Permission[]>

export type Need = keyof typeof NEEDS

/** `PUT /admin/tasks/{id}/status` re-checks by transition: mirrors `admin_service.update_task_status`. */
export const taskStatusNeed = (status: string): Need =>
  status === 'pending' ? 'proposals' : status === 'deleted' ? 'deleteTask' : 'editTask'

export function useCan(): (need: Need) => boolean {
  const { user } = useAuth()
  const held: readonly Permission[] = user?.is_admin ? user.permissions : []
  return (need) => Boolean(user?.is_admin) && (NEEDS[need].length === 0 || NEEDS[need].some((p) => held.includes(p)))
}
