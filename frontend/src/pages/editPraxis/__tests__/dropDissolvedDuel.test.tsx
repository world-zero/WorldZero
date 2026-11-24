// @vitest-environment jsdom
import type { ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { aDuel, aPraxis } from '../../../test/fixtures'

const calls = vi.hoisted(() => [] as string[])
const fixed = vi.hoisted(() => ({ praxis: null as unknown, duel: null as unknown }))

const navigate = vi.hoisted(() => () => {})

vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => navigate,
}))
vi.mock('../../../api/praxis', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/praxis')>()),
  takeJustCreatedPraxis: () => null,
  getPraxis: vi.fn(async () => fixed.praxis),
  deletePraxis: vi.fn(async () => void calls.push('delete')),
}))
vi.mock('../../../api/duel', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/duel')>()),
  getDuelDetail: vi.fn(async () => fixed.duel),
  cancelChallenge: vi.fn(async () => void calls.push('cancel')),
}))
vi.mock('../../../api/tasks', () => ({ getTask: vi.fn(async () => ({})) }))
vi.mock('../../../api/metatasks', () => ({ listMetatasks: vi.fn(async () => []) }))
vi.mock('../../../hooks/useGameConfig', () => ({ useGameConfig: () => null }))
const auth = vi.hoisted(() => ({
  user: { character: { id: 3 } },
  loading: false,
  refetch: async () => {},
}))
vi.mock('../../../auth/AuthContext', () => ({ useAuth: () => auth }))

import { useEditPraxis } from '../useEditPraxis'

const wrapper = ({ children }: { children: ReactNode }) => <MemoryRouter>{children}</MemoryRouter>

beforeEach(() => {
  calls.length = 0
  fixed.praxis = aPraxis({ status: 'in_progress', duel_id: 7 })
  fixed.duel = aDuel({ state: 'dissolved' })
})

it('dropping a dissolved-duel side deletes the praxis without cancelChallenge', async () => {
  const { result } = renderHook(() => useEditPraxis('1'), { wrapper })
  await waitFor(() => expect(result.current.duel?.state).toBe('dissolved'))

  let dropped: Promise<void> | undefined
  act(() => {
    dropped = result.current.cancel()
  })
  await waitFor(() => expect(result.current.pendingConfirm).not.toBeNull())
  await act(async () => {
    result.current.acceptConfirm()
    await dropped
  })

  expect(calls).toEqual(['delete'])
})
