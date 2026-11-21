// @vitest-environment jsdom
/**
 * The empty roster's "Clear all filters" button (#3943, #3956).
 *
 * SEAM: the mounted page at each form factor; the filters are component state.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '../../../i18n'
import type { CharacterOut } from '../../../api/auth'

vi.mock('../../../hooks/useFactions', () => ({ useFactions: () => [] }))
vi.mock('../../../hooks/useTheme', () => ({ useTheme: () => ({ theme: 'dark', toggle: () => {} }) }))
vi.mock('../../../hooks/useFormFactor', async () => (await import('./formFactorMock')).mockModule)

import { DesktopPlayers, MobilePlayers } from './playersAt'
import { NO_RELATIONSHIPS, rankPlayers, type PlayersViewProps } from '../playersData'

function player(id: number, display_name: string, score: number): CharacterOut {
  return {
    id, username: display_name.toLowerCase(), display_name, bio: '', tagline: '', avatar_url: '',
    location: '', level: 3, score, all_time_score: score, faction_slug: 'everymen', status: 'active',
    created_at: '2026-01-01T00:00:00Z', badges: [], invitations: [],
  }
}

const view = (field: CharacterOut[]): PlayersViewProps => ({
  ranked: rankPlayers(field, 'era'),
  scoreMode: 'era',
  onScoreMode: () => {},
  eyebrow: 'Test',
  myCharId: null,
  related: NO_RELATIONSHIPS,
  latest: {},
})

// Three on the podium leave the roster empty by default; a fourth fills it.
const PODIUM_ONLY = [player(1, 'Ada', 400), player(2, 'Bea', 300), player(3, 'Cy', 200)]
const WITH_ROSTER = [...PODIUM_ONLY, player(4, 'Dov', 100)]

vi.stubGlobal('matchMedia', () => ({
  matches: false,
  addEventListener: () => {},
  removeEventListener: () => {},
}))

afterEach(cleanup)

describe.each([
  ['desktop', DesktopPlayers],
  ['mobile', MobilePlayers],
])('%s empty roster', (name, Surface) => {
  const mount = (field: CharacterOut[]) =>
    render(<MemoryRouter><Surface {...view(field)} /></MemoryRouter>)
  const searchBox = () => screen.getByRole('searchbox') as HTMLInputElement
  const action = () => document.querySelector('.filter-empty__action')

  it('offers the clear button for a search nobody matches, and clicking it restores the defaults', () => {
    mount(WITH_ROSTER)
    expect(action()).toBeNull()
    fireEvent.change(searchBox(), { target: { value: 'zzzz' } })
    expect(document.querySelector('.filter-empty')).not.toBeNull()
    expect(action(), name).not.toBeNull()
    fireEvent.click(action()!)
    expect(searchBox().value).toBe('')
    expect(action()).toBeNull()
    expect(screen.getByText('Dov')).toBeTruthy()
  })

  it('shows the podium line, not the filter empty state, when the defaults are on', () => {
    mount(PODIUM_ONLY)
    expect(document.querySelector('.filter-empty')).toBeNull()
    expect(screen.getByText("Everyone's on the podium so far.")).toBeTruthy()
    expect(screen.getByText('3 players')).toBeTruthy()
  })
})
