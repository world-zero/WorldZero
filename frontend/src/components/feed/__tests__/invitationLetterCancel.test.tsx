// @vitest-environment jsdom
/** Cancelling the letter's confirm returns focus to Accept and keeps Cancel dressed like Confirm. Seam: the letter + JoinConfirm. */
import { render, fireEvent, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import '../../../i18n'
import { AuthContext } from '../../../auth/AuthContext'
import FeedCardInvitationLetter from '../FeedCardInvitationLetter'
import type { ActivityFeedItem } from '../../../api/activityFeed'
import type { CurrentUser } from '../../../api/auth'

const letter: ActivityFeedItem = {
  type: 'invitation_letter',
  item_key: 'invitation_letter:1',
  timestamp: '2026-01-01T00:00:00Z',
  actor_display_name: 'Ada',
  actor_faction_slug: null,
  actor_avatar_url: null,
  payload: { faction_slug: 'snide' },
  context_faction_slug: 'snide',
}

afterEach(cleanup)

describe('invitation letter confirm', () => {
  it('Cancel wears .feed-action and hands focus back to Accept', () => {
    const user = { character: { faction_slug: 'coven' } } as unknown as CurrentUser
    const { container } = render(
      <AuthContext.Provider value={{ user, loading: false, refetch: async () => {}, applyUser: () => {}, signOut: async () => {} }}>
        <MemoryRouter>
          <FeedCardInvitationLetter item={letter} />
        </MemoryRouter>
      </AuthContext.Provider>,
    )
    fireEvent.click(container.querySelector('[data-invitation-accept]')!)
    const cancel = container.querySelector('[data-join="cancel"]')!
    expect(cancel.classList.contains('feed-action')).toBe(true)
    fireEvent.click(cancel)
    expect(document.activeElement).toBe(container.querySelector('[data-invitation-accept]'))
  })
})
