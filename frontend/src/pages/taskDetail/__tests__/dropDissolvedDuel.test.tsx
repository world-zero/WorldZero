// @vitest-environment jsdom
/** Dropping a dissolved duel's side skips cancelChallenge, which the backend 400s. Seam: useTaskDetail.confirmDrop. */
import type { ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { aPraxisCard } from '../../../test/fixtures'

const calls = vi.hoisted(() => [] as string[])

vi.mock('../../../auth/AuthContext', () => ({ useAuth: () => ({ user: { character: { id: 1 } } }) }))
vi.mock('../../../hooks/useGameConfig', () => ({ useGameConfig: () => null }))
vi.mock('../../../api/tasks', () => ({ getTask: vi.fn(async () => ({ id: 9 })) }))
vi.mock('../../../api/comments', () => ({ listComments: vi.fn(async () => []) }))
vi.mock('../../../api/relationships', () => ({ listRelationships: vi.fn(async () => []) }))
vi.mock('../../../api/duel', () => ({
  cancelChallenge: vi.fn(async () => void calls.push('cancel')),
  getDuelDetail: vi.fn(async () => ({ state: 'dissolved' })),
}))
vi.mock('../../../api/praxis', () => ({
  deletePraxis: vi.fn(async () => void calls.push('delete')),
  listPraxes: vi.fn(async (q: { status: string }) =>
    q.status === 'in_progress'
      ? [aPraxisCard({ task_id: 9, status: 'in_progress', submitted_at: null, duel_id: 5 })]
      : [],
  ),
}))

import { useTaskDetail } from '../useTaskDetail'

it('drops a dissolved-duel side with delete only', async () => {
  const wrapper = ({ children }: { children: ReactNode }) => <MemoryRouter>{children}</MemoryRouter>
  const { result } = renderHook(() => useTaskDetail('9'), { wrapper })
  await waitFor(() => expect(result.current.loading).toBe(false))
  await waitFor(() => expect(result.current.canDrop).toBe(true))
  act(() => result.current.handleDrop())
  await act(async () => result.current.dropConfirm?.onConfirm())
  expect(calls).toEqual(['delete'])
})
