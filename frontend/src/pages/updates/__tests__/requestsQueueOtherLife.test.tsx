// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import '../../../i18n'

const mocks = vi.hoisted(() => ({
  setActive: vi.fn(async () => ({ id: 1 })),
  applyUser: vi.fn(),
}))
vi.mock('../useRequestsQueue', () => ({
  useRequestsQueue: () => ({ items: [], loading: false, error: null, refresh: () => {} }),
}))
vi.mock('../../../hooks/useSidebarPanels', () => ({
  useSidebarPanels: () => ({
    other_lives_pending: [{ character_id: 7, display_name: 'Life One', pending_requests_count: 2 }],
  }),
}))
vi.mock('../../../auth/AuthContext', () => ({ useAuth: () => ({ applyUser: mocks.applyUser }) }))
vi.mock('../../../api/me', () => ({ setActiveCharacter: mocks.setActive }))

import RequestsQueue from '../RequestsQueue'

describe('the sibling-life line (#3776)', () => {
  it('is a button naming the life, and tapping it switches to that life', async () => {
    render(
      <MemoryRouter>
        <RequestsQueue />
      </MemoryRouter>,
    )
    const button = screen.getByRole('button', { name: '2 waiting on Life One' })
    expect(button.className).toContain('hit-box')
    fireEvent.click(button)
    await waitFor(() => expect(mocks.setActive).toHaveBeenCalledWith(7))
    await waitFor(() => expect(mocks.applyUser).toHaveBeenCalled())
  })
})
