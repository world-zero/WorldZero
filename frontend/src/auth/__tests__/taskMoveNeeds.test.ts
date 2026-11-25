import { describe, it, expect } from 'vitest'
import { NEEDS, taskMoveNeeds } from '../permissions'

// Same rows as test_task_status_permission_follows_the_pair in backend/tests/integration/test_admin_permissions.py.
const RP = 'review_proposals'
const MT = 'manage_tasks'
const DT = 'delete_import_tasks'
const ROWS: [string[], string, string, boolean][] = [
  [[RP], 'pending', 'backdoor', false],
  [[RP], 'pending', 'deleted', false],
  [[RP], 'pending', 'active', true],
  [[RP], 'pending', 'retired', true],
  [[MT], 'pending', 'backdoor', false],
  [[MT, RP], 'pending', 'backdoor', true],
  [[DT], 'pending', 'deleted', true],
  [[DT], 'deleted', 'pending', true],
  [[RP], 'deleted', 'pending', false],
  [[MT], 'active', 'retired', true],
  [[RP], 'active', 'retired', false],
]

describe('taskMoveNeeds', () => {
  it.each(ROWS)('held %j: %s -> %s allowed=%s', (held, from, to, allowed) => {
    const ok = taskMoveNeeds(from, to).every((n) => NEEDS[n].length === 0 || NEEDS[n].some((p) => held.includes(p)))
    expect(ok).toBe(allowed)
  })
})
