import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import FeedCardDuelChallenge from '../FeedCardDuelChallenge'
import type { ActivityFeedItem } from '../../../api/activityFeed'

vi.mock('../../../hooks/useRespondToRequest', () => ({
  useRespondToRequest: () => ({
    accept: vi.fn(),
    decline: vi.fn(),
    loading: false,
    status: 'pending',
    error: '',
  }),
}))
vi.mock('../../../hooks/useMyActiveTasks', () => ({
  useMyActiveTasks: () => ({ activeTasks: [], refetch: vi.fn() }),
}))
vi.mock('../../../hooks/useGameConfig', () => ({ useGameConfig: () => null }))
vi.mock('../../../auth/AuthContext', () => ({ useAuth: () => ({ user: null }) }))

const item = {
  type: 'duel_challenge',
  item_key: 'duel_challenge:7',
  timestamp: '2026-01-01T00:00:00Z',
  actor_display_name: 'Ada',
  actor_faction_slug: 'coven',
  actor_avatar_url: null,
  payload: {
    duel_id: 7,
    challenger_praxis_id: 9,
    challenger_character_id: 3,
    task_title: 'Build a shed',
    task_point_value: 40,
    task_faction_slug: 'coven',
  },
  context_faction_slug: 'coven',
} as unknown as ActivityFeedItem

const html = renderToStaticMarkup(
  <MemoryRouter>
    <FeedCardDuelChallenge item={item} />
  </MemoryRouter>,
)

describe('duel challenge card', () => {
  it('draws the swords as SVG, never the U+2694 glyph', () => {
    expect(html).not.toContain('⚔')
    expect(html).toContain('<svg')
  })

  it('has no duel badge and offers only Accept Duel and Decline', () => {
    expect(html).not.toContain('>Duel<')
    expect(html).not.toContain('Withdraw')
    expect(html.match(/<button/g)).toHaveLength(2)
  })
})

describe("catalogs", () => {
  it("carry no U+2694 (tofu on faces without it)", () => {
    const catalogs = import.meta.glob("../../../locales/en/*.json", { eager: true })
    expect(Object.keys(catalogs).length).toBeGreaterThan(5)
    for (const [f, json] of Object.entries(catalogs)) {
      expect(JSON.stringify(json), f).not.toContain("\u2694")
    }
  })
})
