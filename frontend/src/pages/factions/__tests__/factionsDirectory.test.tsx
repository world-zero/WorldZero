/**
 * The factions directory, one responsive page (#3800). Seam: the component fed a
 * controlled state, since effects never fire in this harness.
 *
 * The "Recent Invitations" panel is gone (#2310); the load-bearing guard is
 * that an `invited` status alone still reads `eligible` on desktop.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import { describe, it, expect } from 'vitest'
import '../../../i18n'
import i18n from '../../../i18n'
import type { FactionOut, FactionPageOut, FactionStatusOut, InvitationLetterOut } from '../../../api/factions'
import type { CurrentUser } from '../../../api/auth'
import { AuthContext } from '../../../auth/AuthContext'
import { FactionsDirectory } from '../../Factions'

function render(element: ReactElement): { html: string; text: string } {
  const html = renderToStaticMarkup(<MemoryRouter>{element}</MemoryRouter>)
  return { html, text: decode(html.replace(/<[^>]*>/g, '')) }
}

/** Unescape markup so catalog strings (e.g. "Let's …") compare directly. */
function decode(value: string): string {
  return value
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

/** A tile's status line from the catalog. Literal unions keep the key typed. */
type StatusSlug = 'coven' | 'snide' | 'everymen'
type StatusState = 'locked' | 'eligible' | 'member'

function statusLine(slug: StatusSlug, state: StatusState): string {
  return i18n.t(`feed:factionSelect.${slug}.status.${state}` as const)
}

// What an unrevealed player gets (ADR-0027: no Albescent), out of rainbow
// order and carrying `na` — the shape behind the 7-stripes-over-6-cards bug.
const FACTIONS: FactionOut[] = [
  { slug: 'coven', status: 'visible' },
  { slug: 'everymen', status: 'visible' },
  { slug: 'snide', status: 'visible' },
  { slug: 'na', status: 'visible' },
  { slug: 'ua', status: 'visible' },
  { slug: 'ephemerists', status: 'visible' },
  { slug: 'singularity', status: 'visible' },
]

function status(
  rows: Array<[string, FactionStatusOut['status']]>,
  invitations: InvitationLetterOut[] = [],
): FactionPageOut {
  const all_factions: FactionStatusOut[] = rows.map(([slug, status]) => ({ slug, status, joinable: false, refusal: null }))
  return { current_faction_slug: 'coven', all_factions, invitations }
}

// One of each card state: Coven member, S.N.I.D.E. invited, Everymen not.
const STATUS = status([
  ['coven', 'member'],
  ['snide', 'invited'],
  ['everymen', 'not_invited'],
  ['ua', 'not_invited'],
  ['ephemerists', 'not_invited'],
  ['singularity', 'not_invited'],
])

const LETTERS: InvitationLetterOut[] = [
  { faction_slug: 'snide', delivered_at: '2026-01-01T00:00:00Z' },
  { faction_slug: 'coven', delivered_at: '2026-01-02T00:00:00Z' },
]

const VIEWER = (faction_slug: string | null) => ({ character: { faction_slug } }) as unknown as CurrentUser

function dir(
  page: FactionPageOut | null,
  over: { user?: CurrentUser | null; loading?: boolean; error?: unknown; factions?: FactionOut[] } = {},
) {
  return render(
    <AuthContext.Provider
      value={{
        user: over.user === undefined ? VIEWER('coven') : over.user,
        loading: false,
        refetch: async () => {},
        applyUser: () => {},
        signOut: async () => {},
      }}
    >
      <FactionsDirectory
        state={{ factions: over.factions ?? FACTIONS, factionPage: page, loading: over.loading ?? false, error: over.error ?? null }}
      />
    </AuthContext.Provider>,
  )
}

const rows = (page: FactionPageOut) => page.all_factions.map((r): [string, FactionStatusOut['status']] => [r.slug, r.status])

describe('factions directory', () => {
  it('draws one card per faction, na dropped', () => {
    expect((dir(STATUS).html.match(/<button/g) ?? []).length).toBe(6)
  })

  it('keeps rainbow order, not member-first', () => {
    const { html } = dir(STATUS)
    const order = ['everymen', 'ua', 'ephemerists', 'snide', 'singularity', 'coven']
    const positions = order.map((slug) => html.indexOf(`faction-${slug}`))
    for (const pos of positions) expect(pos).toBeGreaterThan(-1)
    expect(positions).toEqual([...positions].sort((a, b) => a - b))
  })

  it('reads member / eligible / locked from status alone, letters or not', () => {
    const withLetters = dir(status(rows(STATUS), LETTERS))
    expect(withLetters.text).toContain(statusLine('coven', 'member'))
    expect(withLetters.text).toContain(statusLine('snide', 'eligible'))
    expect(withLetters.text).toContain(statusLine('everymen', 'locked'))
    expect(withLetters.text).not.toContain('Recent Invitations')
    expect(withLetters.html).not.toContain('aria-expanded')
    expect(dir(STATUS).text).toBe(withLetters.text)
  })

  it('falls back to locked when a faction has no status row', () => {
    const { text } = dir(status([]))
    expect(text).toContain(statusLine('coven', 'locked'))
  })

  it('dims a defected faction', () => {
    const { html } = dir(status([['coven', 'defected']]))
    expect(html).toContain('opacity:0.5')
  })

  it('tells a defected faction in platform words, never the faction voice (#4245)', () => {
    const { text } = dir(status([['everymen', 'defected']]))
    expect(text).toContain(i18n.t('feed:factionSelectBurned.status'))
    expect(text).toContain(i18n.t('feed:factionSelectBurned.cta'))
    expect(text).not.toContain(statusLine('everymen', 'locked'))
    expect(text).not.toContain(i18n.t('feed:factionSelect.everymen.cta'))
  })

  it('shows loading and error states without cards', () => {
    expect(dir(null, { loading: true }).html).not.toContain('<button')
    const err = dir(STATUS, { error: new Error('Boom') })
    expect(err.text).toContain('Unable to reach the server')
  })

  it('signed out: hint, no banner; no faction: banner; with faction: neither', () => {
    const out = dir(null, { user: null })
    expect(out.text).toContain(i18n.t('factions:index.loggedOutHint'))
    expect(out.html).not.toContain('sidebar-card')
    const none = dir(STATUS, { user: VIEWER(null) })
    expect(none.html).toContain('sidebar-card')
    expect(none.text).not.toContain(i18n.t('factions:index.loggedOutHint'))
    const member = dir(STATUS)
    expect(member.html).not.toContain('sidebar-card')
  })

  it('unaffiliated banner leads with the na ring, not an empty disc', () => {
    const { html } = dir(STATUS, { user: VIEWER(null) })
    expect(html).toContain('--faction-default-rainbow-conic')
    expect(html).not.toContain('unaffiliated-banner-disc')
  })

  it('stretches the row and makes each tile wrapper a column, so calls line up (#3139)', () => {
    const { html } = dir(STATUS)
    const at = html.indexOf('data-testid="faction-tile-row"')
    expect(at).toBeGreaterThan(-1)
    const row = html.slice(html.lastIndexOf('<', at), html.indexOf('>', at) + 1)
    expect(row).toMatch(/class="[^"]*\bfaction-tile-row\b/)
    expect(html.match(/<div class="faction-tile" style="opacity:[^"]*">/g) ?? []).toHaveLength(6)
  })

  it('centres the tile row on phones, left-aligns from md up (#2579)', () => {
    const { html } = dir(STATUS)
    const at = html.indexOf('data-testid="faction-tile-row"')
    const row = html.slice(html.lastIndexOf('<', at), html.indexOf('>', at) + 1)
    expect(row).toContain('justify-center')
  })
})
