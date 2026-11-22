import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect } from 'vitest'
import FeedRowContent from '../FeedRowContent'
import { normalizeFeedItem } from '../normalizeFeedItem'
import common from '../../../locales/en/common.json'
import type { ActivityFeedItem } from '../../../api/activityFeed'

const item = {
  type: 'duel_live',
  item_key: 'duel_live:7',
  timestamp: '2026-01-01T00:00:00Z',
  actor_display_name: 'Ada',
  actor_faction_slug: 'coven',
  actor_avatar_url: null,
  payload: {
    duel_id: 7,
    challenger_character_id: 3,
    opponent_character_id: 4,
    opponent_display_name: 'Bram',
    opponent_faction_slug: 'snide',
    opponent_avatar_url: '',
    task_title: 'Build a shed',
    task_point_value: 40,
    task_faction_slug: 'coven',
  },
  context_faction_slug: 'coven',
} as unknown as ActivityFeedItem

describe('duel_live row', () => {
  it('names both duelists and sends the vote to the duel page', () => {
    const row = normalizeFeedItem(item)
    if (!row) throw new Error('duel_live has no row')
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <FeedRowContent row={row} avatarUrl={null} />
      </MemoryRouter>,
    )
    expect(html).toContain('Ada')
    expect(html).toContain('Bram')
    expect(html).toContain('Build a shed')
    expect(html).toContain('href="/duel/7"')
    expect(row.actions.map((action) => action.href)).toEqual(['/duel/7'])
    expect(html).not.toContain('duelLive')
  })

  it('labels an absent opponent, not the blanked name', () => {
    const row = normalizeFeedItem({
      ...item,
      payload: { ...item.payload, opponent_display_name: '', opponent_name_state: 'absent' },
    } as ActivityFeedItem)
    expect(row?.action).toContain(common.absentPlayer)
  })

  it('writes the taunt from the labelled actor when the sender is absent', () => {
    const row = normalizeFeedItem({
      type: 'foe_taunt',
      item_key: 'foe_taunt:1',
      timestamp: '2026-01-01T00:00:00Z',
      actor_display_name: common.absentPlayer,
      actor_name_state: 'absent',
      actor_faction_slug: 'snide',
      payload: { from_name: '', to_name: 'Ada', faction_slug: 'snide', trigger_type: 'level_up', taunt_id: 0 },
      context_faction_slug: 'snide',
    } as unknown as ActivityFeedItem)
    expect(row?.actorHref).toBeNull()
    expect(row?.headline).toContain(common.absentPlayer)
  })
})
