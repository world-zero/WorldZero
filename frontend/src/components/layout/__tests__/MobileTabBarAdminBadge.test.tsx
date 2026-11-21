// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import '../../../i18n'
import MobileTabBar from '../MobileTabBar'

vi.mock('../../../auth/AuthContext', () => ({
  useAuth: () => ({ user: { is_admin: true, character: { id: 1, username: 'A', faction_slug: 'snide', level: 1 } } }),
}))
vi.mock('../../../hooks/useSidebarPanels', () => ({ useSidebarPanels: () => ({ pending_requests_count: 0 }) }))
vi.mock('../../../pages/admin/useAdminCounts', async (orig) => ({
  ...(await orig<object>()),
  useAdminCounts: () => ({ reports: 4, messages: 5, proposals: 2, reload: () => {} }),
}))

describe('You tab badge for an admin', () => {
  it('shows the mod queue total with no requests and names both parts', async () => {
    render(
      <MemoryRouter>
        <MobileTabBar />
      </MemoryRouter>,
    )
    const you = await screen.findByRole('button', { name: 'You: 11 moderation items' })
    expect(you.textContent).toContain('11')
  })
})
