// @vitest-environment jsdom
/** #4193: regaining the tab refetches the rail once; a request push rings the bus. */
import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

vi.mock('../../auth/AuthContext', () => ({ useAuth: () => ({ user: null, loading: false }) }))
vi.mock('../../api/sidebar', () => ({ getSidebar: vi.fn(async () => ({})) }))

import { getSidebar } from '../../api/sidebar'
import { onRequestsChanged, onSwMessage } from '../../utils/requestsBus'
import { SidebarProvider } from '../useSidebarPanels'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

function setVisibility(v: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { value: v, configurable: true })
  document.dispatchEvent(new Event('visibilitychange'))
}

it('a visibilitychange + focus burst to visible is one refetch; hidden is none', async () => {
  render(<SidebarProvider>{null}</SidebarProvider>)
  await act(async () => {})
  vi.mocked(getSidebar).mockClear()
  await act(async () => {
    setVisibility('hidden')
    window.dispatchEvent(new Event('focus'))
    await vi.advanceTimersByTimeAsync(500)
  })
  expect(getSidebar).not.toHaveBeenCalled()
  await act(async () => {
    setVisibility('visible')
    window.dispatchEvent(new Event('focus'))
    await vi.advanceTimersByTimeAsync(500)
  })
  expect(getSidebar).toHaveBeenCalledTimes(1)
})

it('only a request-push message rings the bus', () => {
  const fn = vi.fn()
  const off = onRequestsChanged(fn)
  onSwMessage({ data: { type: 'other' } })
  expect(fn).not.toHaveBeenCalled()
  onSwMessage({ data: { type: 'wz-request-push' } })
  expect(fn).toHaveBeenCalledTimes(1)
  off()
})
