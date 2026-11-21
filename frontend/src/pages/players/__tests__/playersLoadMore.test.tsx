// @vitest-environment jsdom
/**
 * The roster's load-more button (#3969, #3980).
 *
 * SEAM: the mounted page at each form factor, past one roster page.
 */
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '../../../i18n'
import type { CharacterOut } from '../../../api/auth'

vi.mock('../../../hooks/useFactions', () => ({ useFactions: () => [] }))
vi.mock('../../../hooks/useTheme', () => ({ useTheme: () => ({ theme: 'dark', toggle: () => {} }) }))
vi.mock('../../../hooks/useFormFactor', async () => (await import('./formFactorMock')).mockModule)

import { DesktopPlayers, MobilePlayers } from './playersAt'
import { NO_RELATIONSHIPS, ROSTER_PAGE_STEP, rankPlayers, type PlayersViewProps } from '../playersData'

const PODIUM = 3
const EXTRA = 5
const field: CharacterOut[] = Array.from({ length: PODIUM + ROSTER_PAGE_STEP + EXTRA }, (_, i) => ({
  id: i + 1, username: `p${i}`, display_name: `P${i}`, bio: '', tagline: '', avatar_url: '',
  location: '', level: 3, score: 1000 - i, all_time_score: 1000 - i, faction_slug: 'everymen',
  status: 'active', created_at: '2026-01-01T00:00:00Z', badges: [], invitations: [],
}))

const view: PlayersViewProps = {
  ranked: rankPlayers(field, 'era'),
  scoreMode: 'era',
  onScoreMode: () => {},
  eyebrow: 'Test',
  myCharId: null,
  related: NO_RELATIONSHIPS,
  latest: {},
}

vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }))

afterEach(cleanup)

const mount = (Surface: typeof DesktopPlayers) =>
  render(<MemoryRouter><Surface {...view} /></MemoryRouter>)

describe('roster load-more', () => {
  it('phone: counts what is left, full width, bordered pill', () => {
    mount(MobilePlayers)
    const btn = screen.getByRole('button', { name: `${EXTRA} more players` })
    expect(btn.className).toContain('w-full md:w-auto')
    expect(btn.style.border).toContain('var(--color-border-strong)')
    expect(btn.style.borderRadius).toBe('999px')
  })

  it('desktop: plain "Load more"', () => {
    mount(DesktopPlayers)
    expect(screen.getByRole('button', { name: /^load more$/i })).toBeTruthy()
  })
})
