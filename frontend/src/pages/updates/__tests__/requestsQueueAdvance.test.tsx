// @vitest-environment jsdom
/** Seam: RequestsQueue's archive action advances the cursor and remounts the card. */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '../../../i18n'
import type { ActivityFeedItem } from '../../../api/activityFeed'

const mocks = vi.hoisted(() => ({ items: [] as ActivityFeedItem[] }))
vi.mock('../useRequestsQueue', () => ({
  useRequestsQueue: () => ({ items: mocks.items, loading: false, error: null, refresh: () => {} }),
}))
vi.mock('../../../api/activityFeed', async (orig) => ({
  ...(await orig<object>()),
  dismissFeedItem: vi.fn(async () => {}),
  restoreFeedItem: vi.fn(async () => {}),
}))
vi.mock('../../../auth/AuthContext', () => ({
  useAuth: () => ({ user: { faction_slug: null }, applyUser: vi.fn() }),
}))
vi.mock('../../../hooks/useSidebarPanels', () => ({
  useSidebarPanels: () => ({ other_lives_pending: [] }),
}))

import RequestsQueue from '../RequestsQueue'

window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia

const letter = (id: number, faction: string): ActivityFeedItem => ({
  type: 'invitation_letter',
  item_key: `invitation_letter:${id}`,
  timestamp: '2026-01-01T00:00:00Z',
  actor_display_name: 'Ada',
  actor_faction_slug: faction,
  actor_avatar_url: null,
  payload: { faction_slug: faction },
  context_faction_slug: faction,
})

afterEach(cleanup)

describe('Not now in the Requests queue', () => {
  it('shows the next letter with fresh controls, and the first still counts', async () => {
    mocks.items = [letter(1, 'coven'), letter(2, 'snide')]
    render(<MemoryRouter><RequestsQueue /></MemoryRouter>)
    expect(document.querySelector('[data-feed-slot="invitation_letter:1"]')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /not now/i }))
    await waitFor(() =>
      expect(document.querySelector('[data-feed-slot="invitation_letter:2"]')).not.toBeNull(),
    )
    expect(screen.getByRole('button', { name: /not now/i })).toBeTruthy()
    expect(document.querySelector('[data-feed-slot="invitation_letter:1"]')).toBeNull()
    expect(screen.getByText(/2/, { selector: '.requests-queue__badge' })).toBeTruthy()
  })
})
