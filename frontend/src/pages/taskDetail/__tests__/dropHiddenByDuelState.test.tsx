// @vitest-environment jsdom
/** Task detail hides Drop for a side of a duel that can't be dissolved (Q5, #4200). Seam: useTaskDetail.canDrop. */
import type { ReactNode } from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { aPraxisCard } from '../../../test/fixtures'

const duelState = vi.hoisted(() => ({ value: 'challenged' }))

vi.mock('../../../auth/AuthContext', () => ({ useAuth: () => ({ user: { character: { id: 1 } } }) }))
vi.mock('../../../hooks/useGameConfig', () => ({ useGameConfig: () => null }))
vi.mock('../../../api/tasks', () => ({ getTask: vi.fn(async () => ({ id: 9 })) }))
vi.mock('../../../api/comments', () => ({ listComments: vi.fn(async () => []) }))
vi.mock('../../../api/relationships', () => ({ listRelationships: vi.fn(async () => []) }))
vi.mock('../../../api/duel', () => ({
  cancelChallenge: vi.fn(),
  getDuelDetail: vi.fn(async () => ({ state: duelState.value })),
}))
vi.mock('../../../api/praxis', () => ({
  listPraxes: vi.fn(async (q: { status: string }) =>
    q.status === 'in_progress'
      ? [aPraxisCard({ task_id: 9, status: 'in_progress', submitted_at: null, duel_id: 5 })]
      : [],
  ),
}))

import { useTaskDetail } from '../useTaskDetail'

async function canDropFor(state: string) {
  duelState.value = state
  const wrapper = ({ children }: { children: ReactNode }) => <MemoryRouter>{children}</MemoryRouter>
  const { result } = renderHook(() => useTaskDetail('9'), { wrapper })
  await waitFor(() => expect(result.current.loading).toBe(false))
  // Hidden until the duel is read, so wait out the fetch before judging.
  await new Promise((r) => setTimeout(r, 10))
  return result.current.canDrop
}

describe('useTaskDetail canDrop for a duel side', () => {
  it.each(['awaiting_honest_side', 'live', 'live_forfeited', 'resolved', 'no_contest'])(
    'hides Drop in %s',
    async (state) => expect(await canDropFor(state)).toBe(false),
  )
  it.each(['challenged', 'drafting', 'one_cast'])('shows Drop in %s', async (state) =>
    expect(await canDropFor(state)).toBe(true),
  )
})
