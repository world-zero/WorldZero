/** A blocked author's comment reads as a labelled, bodiless box for the blocker (#3867). */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect } from 'vitest'
import i18n from '../../../i18n'
import type { ActivityFeedItem } from '../../../api/activityFeed'
import type { CommentOut } from '../../../api/comments'
import FeedRowContent from '../../feed/FeedRowContent'
import { normalizeFeedItem } from '../../feed/normalizeFeedItem'
import { DefaultComment } from '../CommentThread'
import { surfaceMap } from '../../../factions'
import { resolvedArchetype } from '../../../factions/lazyArchetype'

const LABEL = i18n.t('common:relationships.censoredComment')

const CENSORED: CommentOut = {
  id: 7,
  praxis_id: 1,
  task_id: null,
  admin_note: null,
  is_censored: true,
  body_text: '',
  is_edited: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  author: { name_state: 'ok', id: 42, username: 'ada', display_name: 'Adabel', avatar_url: '', faction_slug: 'na' },
  mentions: [],
}

describe('censored comment', () => {
  it('keeps the author in the thread and shows the label for the body', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DefaultComment mode="row" comment={CENSORED} />
      </MemoryRouter>,
    )
    expect(html).toContain('Adabel')
    expect(html).toContain(LABEL)
  })

  it.each(Object.keys(surfaceMap('comment')))('%s voice shows the label for the body', (slug) => {
    const Voice = resolvedArchetype(surfaceMap('comment')[slug as keyof ReturnType<typeof surfaceMap<'comment'>>])
    if (!Voice) throw new Error(`no comment voice resolved for "${slug}"`)
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <Voice mode="row" comment={{ ...CENSORED, author: { ...CENSORED.author, faction_slug: slug } }} />
      </MemoryRouter>,
    )
    expect(html).toContain(LABEL)
  })

  it('shows the label unquoted in the feed row', () => {
    const row = normalizeFeedItem({
      type: 'comment_mention',
      item_key: 'comment_mention:7',
      timestamp: '2026-01-01T00:00:00Z',
      actor_display_name: 'Adabel',
      actor_faction_slug: 'na',
      actor_avatar_url: null,
      payload: { comment_id: 7, character_id: 42, praxis_id: 1, excerpt: '', is_censored: true },
      context_faction_slug: 'na',
    } as unknown as ActivityFeedItem)
    if (!row) throw new Error('comment_mention has no row')
    expect(row.headline).toBe(LABEL)
    expect(row.headlineQuoted).toBe(false)
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <FeedRowContent row={row} avatarUrl={null} />
      </MemoryRouter>,
    )
    expect(html).toContain(LABEL)
  })
})
