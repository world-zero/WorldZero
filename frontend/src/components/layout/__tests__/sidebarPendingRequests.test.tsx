/**
 * #1423: the rail lists no pending requests (ADR-0070: answered only in the
 * `/updates` queue) and the fold handle badges nothing (#4131).
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import '../../../i18n'
import i18n from '../../../i18n'
import type { CurrentUser } from '../../../api/auth'

const panelsMock = vi.fn()
vi.mock('../../../hooks/useSidebarPanels', () => ({
  useSidebarPanels: () => panelsMock(),
}))

vi.mock('../../../auth/AuthContext', () => ({
  useAuth: () => ({ user: { character: null } as unknown as CurrentUser, signOut: () => {} }),
}))
vi.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({ theme: 'light', toggle: () => {} }),
}))
vi.mock('../../../api/auth', () => ({ loginWith: () => {} }))
vi.mock('../../../hooks/useGameConfig', () => ({
  useGameConfig: () => null,
}))

import NavBar from '../../NavBar'
import SidebarColumn from '../SidebarColumn'

const PENDING_COUNT = 3

function render(collapsed: boolean): string {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={['/']}>
      <SidebarColumn collapsed={collapsed} onToggle={() => {}} />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  panelsMock.mockReturnValue({
    pending_requests_count: PENDING_COUNT,
    global_activity: [],
    active_praxes: [],
    refetch: vi.fn(),
    loading: false,
  })
})

describe('the rail and its pending requests', () => {
  it('lists no pending request, and offers no way to answer one', () => {
    const html = render(false)

    // Literals: their keys are deleted, and `t()` of a deleted key returns the
    // key itself, which would never match. `actions.*` keys are live (#2598).
    expect(html, 'panel heading').not.toContain('Pending Requests')
    expect(html, 'PendingRequestRow kicker').not.toContain('Collab Invite')
    expect(html, 'PendingRequestRow kicker').not.toContain('Duel Challenge')
    expect(html, 'AwaitingSubmissionRow kicker').not.toContain('Your turn')
    expect(i18n.t('common:actions.accept'), 'guard: key resolves').toBe('Accept')
    expect(html, 'accept').not.toContain(i18n.t('common:actions.accept'))
    expect(html, 'decline').not.toContain(i18n.t('common:actions.decline'))
  })

  // #4131: one badge on screen at desktop width, on Updates, never on the handle.
  it.each([true, false])('draws exactly one badge, on Updates (collapsed=%s)', (collapsed) => {
    panelsMock.mockReturnValue({ ...panelsMock(), pending_requests_count: 1 })
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={['/']}>
        <NavBar />
        <SidebarColumn collapsed={collapsed} onToggle={() => {}} />
      </MemoryRouter>,
    )
    expect(html.match(/min-width:15px/g)).toHaveLength(1)
    expect(html).toContain('aria-label="Updates — 1 pending request"')
    expect(html).not.toContain('sidebar — ')
  })
})
