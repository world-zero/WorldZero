// @vitest-environment jsdom
/** Task detail's failed sign-up reads like the TaskCard's: a 400 with no detail gets the shared `home:signup.error`. Seam: useTaskDetail.handleSignup. */
import type { ReactNode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../../../auth/AuthContext', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('../../../hooks/useGameConfig', () => ({ useGameConfig: () => null }))
vi.mock('../../../api/tasks', () => ({ getTask: vi.fn(async () => ({ id: 9 })) }))
vi.mock('../../../api/comments', () => ({ listComments: vi.fn(async () => []) }))
vi.mock('../../../api/praxis', async () => {
  const { ApiError } = await import('../../../api/apiError')
  return {
    listPraxes: vi.fn(async () => []),
    createPraxis: vi.fn(() => Promise.reject(new ApiError(new Response(null, { status: 400 }), {}))),
  }
})

import i18n from '../../../i18n'
import { useTaskDetail } from '../useTaskDetail'

describe('useTaskDetail handleSignup', () => {
  it('a 400 with no detail shows the shared sign-up wording', async () => {
    const wrapper = ({ children }: { children: ReactNode }) => <MemoryRouter>{children}</MemoryRouter>
    const { result } = renderHook(() => useTaskDetail('9'), { wrapper })
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(() => result.current.handleSignup())
    expect(result.current.signupError).toBe(i18n.t('home:signup.error'))
  })
})
