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

const MOVE_TARGETS = ['active', 'retired', 'backdoor', 'deleted']

/** Every box `PUT /admin/tasks/{id}/status` wants for a (from, to) move: mirrors `admin_service.update_task_status`. */
export const taskMoveNeeds = (from: string, to: string): Need[] =>
  from === 'deleted' || to === 'deleted'
    ? ['deleteTask']
    : from === 'pending'
      ? to === 'backdoor' ? ['proposals', 'editTask'] : ['proposals']
      : ['editTask']

/** `canMove(from, to)`; without `to`, whether any move out of `from` is allowed. */
export function useCanMove(): (from: string, to?: string) => boolean {
  const can = useCan()
  return (from, to) =>
    (to ? [to] : MOVE_TARGETS).some((target) => taskMoveNeeds(from, target).every(can))
}

export function useCan(): (need: Need) => boolean {
  const { user } = useAuth()
  const held: readonly Permission[] = user?.is_admin ? user.permissions : []
  return (need) => Boolean(user?.is_admin) && (NEEDS[need].length === 0 || NEEDS[need].some((p) => held.includes(p)))
}
