/** The feed card reads `feed:invitationLetter.<slug>.*` first, then the shared key (#4133). */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, it, expect } from 'vitest'
import i18n from '../../../i18n'
import { AuthContext } from '../../../auth/AuthContext'
import FeedCardInvitationLetter from '../FeedCardInvitationLetter'
import type { ActivityFeedItem } from '../../../api/activityFeed'
import type { CurrentUser } from '../../../api/auth'

function render(slug: string): string {
  const item = {
    type: 'invitation_letter', item_key: 'k', timestamp: '2026-01-01T00:00:00Z',
    actor_display_name: '', actor_faction_slug: null, actor_avatar_url: null,
    payload: { faction_slug: slug }, context_faction_slug: slug,
  } as ActivityFeedItem
  const user = { character: { faction_slug: 'na' } } as unknown as CurrentUser
  return renderToStaticMarkup(
    <AuthContext.Provider value={{ user, loading: false, refetch: async () => {}, applyUser: () => {}, signOut: async () => {} }}>
      <MemoryRouter><FeedCardInvitationLetter item={item} /></MemoryRouter>
    </AuthContext.Provider>,
  )
}

const covenBody = i18n.t('feed:invitationLetter.coven.body')
afterEach(() => {
  i18n.addResource('en', 'feed', 'invitationLetter.coven.body', covenBody)
})

describe('invitation card faction copy', () => {
  it('an override for coven changes only the coven card', () => {
    const shared = i18n.t('feed:invitationLetter.snide.body')
    i18n.addResource('en', 'feed', 'invitationLetter.coven.body', 'Come to the table.')
    expect(render('coven')).toContain('Come to the table.')
    expect(render('snide')).toContain(shared)
    expect(render('snide')).not.toContain('Come to the table.')
  })

  it('a faction with no key shows the shared text', () => {
    expect(render('no-such-faction')).toContain(i18n.t('feed:invitationLetter.body'))
  })
})
