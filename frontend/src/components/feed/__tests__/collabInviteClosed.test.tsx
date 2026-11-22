// @vitest-environment jsdom
/** A collab invite whose praxis was submitted without you resolves itself (#4188). */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import i18n from '../../../i18n'
import { ApiError } from '../../../api/apiError'
import FeedCardCollabInvite from '../FeedCardCollabInvite'
import { isInvitePraxisSubmitted } from '../inviteClosed'
import type { ActivityFeedItem } from '../../../api/activityFeed'

const respondToInvite = vi.hoisted(() => vi.fn())
vi.mock('../../../api/praxis', () => ({
  respondToInvite,
  deletePraxis: vi.fn(),
  leavePraxis: vi.fn(),
}))
vi.mock('../../../auth/AuthContext', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('../../../hooks/useMyActiveTasks', () => ({
  useMyActiveTasks: () => ({ activeTasks: [], refetch: vi.fn() }),
}))
vi.mock('../../../hooks/useGameConfig', () => ({ useGameConfig: () => null }))

const apiError = (status: number, detail: unknown) =>
  new ApiError(new Response(null, { status }), { detail })

const item = {
  type: 'collab_invite',
  item_key: 'collab_invite:3',
  timestamp: '2026-01-01T00:00:00Z',
  actor_display_name: 'Robin',
  actor_faction_slug: null,
  actor_avatar_url: null,
  payload: {
    praxis_id: 12,
    invite_id: 3,
    task_title: 'Build a shed',
    task_point_value: 5,
    task_level_required: 1,
    inviter_character_id: 4,
  },
} as unknown as ActivityFeedItem

const ACCEPT = i18n.t('common:actions.accept')
const DECLINE = i18n.t('common:actions.decline')
const mount = () =>
  render(
    <MemoryRouter>
      <FeedCardCollabInvite item={item} />
    </MemoryRouter>,
  )

afterEach(() => {
  cleanup()
  respondToInvite.mockReset()
})

describe('collab invite on an already-submitted praxis', () => {
  it('matches the code, not the prose', () => {
    expect(isInvitePraxisSubmitted(apiError(400, { code: 'INVITE_PRAXIS_SUBMITTED', message: 'x' }))).toBe(true)
    expect(isInvitePraxisSubmitted(apiError(500, 'Internal Server Error'))).toBe(false)
  })

  it('swaps Accept and Decline for the closed caption', async () => {
    respondToInvite.mockRejectedValue(
      apiError(400, { code: 'INVITE_PRAXIS_SUBMITTED', message: 'Cannot join a submitted praxis.' }),
    )
    mount()
    fireEvent.click(screen.getByText(ACCEPT))
    const caption = await screen.findByText(i18n.t('feed:collabInvite.closed'))
    expect(caption.closest('a')?.getAttribute('href')).toBe('/praxis/12')
    expect(screen.queryByText(ACCEPT)).toBeNull()
    expect(screen.queryByText(DECLINE)).toBeNull()
  })

  it('keeps the buttons and the error on a generic 500', async () => {
    respondToInvite.mockRejectedValue(apiError(500, 'Internal Server Error'))
    mount()
    fireEvent.click(screen.getByText(ACCEPT))
    await waitFor(() => expect(respondToInvite).toHaveBeenCalledTimes(2))
    expect(screen.getByText(ACCEPT)).toBeTruthy()
    expect(screen.getByText(DECLINE)).toBeTruthy()
    expect(screen.queryByText(i18n.t('feed:collabInvite.closed'))).toBeNull()
  })
})
