// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import '../../../i18n'
import type { CharacterOut } from '../../../api/auth'

const mocks = vi.hoisted(() => ({
  getLeaderboard: vi.fn(),
  getLeaderboardEra: vi.fn(),
}))

vi.mock('../../../hooks/useTheme', () => ({ useTheme: () => ({ theme: 'dark', toggle: () => {} }) }))
vi.mock('../../../auth/AuthContext', () => ({ useAuth: () => ({ user: null }) }))
vi.mock('../../../hooks/useGameConfig', () => ({ useGameConfig: () => ({ era_name: 'Current Era' }) }))
vi.mock('../../../hooks/useFormFactor', () => ({ useFormFactor: () => 'desktop', usePhoneWidth: () => false }))
vi.mock('../../../api/leaderboard', () => mocks)
vi.mock('../../../api/praxis', () => ({ listPraxes: async () => [] }))
vi.mock('../../../api/relationships', () => ({ listRelationships: async () => [] }))
vi.mock('../../../api/me', () => ({ getNearbyAirports: async () => null }))

import Leaderboard from '../../Leaderboard'

const WREN = {
  id: 1, username: 'wren', display_name: 'Wren', bio: '', tagline: '', avatar_url: '', location: '',
  level: 3, score: 320, all_time_score: 900, faction_slug: 'everymen', status: 'active',
  created_at: '2026-01-01T00:00:00Z', badges: [], invitations: [],
} as unknown as CharacterOut

const at = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Leaderboard />
    </MemoryRouter>,
  )

describe('/leaderboard?era= (#4301)', () => {
  afterEach(cleanup)
  beforeEach(() => {
    mocks.getLeaderboard.mockReset().mockResolvedValue([WREN])
    mocks.getLeaderboardEra.mockReset().mockResolvedValue({ id: 3, name: 'Renaissance' })
  })

  it('sends the era to the API, labels it, and drops the faction race', async () => {
    at('/leaderboard?era=3')
    expect(await screen.findByText('Renaissance')).toBeTruthy()
    expect(mocks.getLeaderboard).toHaveBeenCalledWith({ limit: 500, era: 3 })
    expect(mocks.getLeaderboardEra).toHaveBeenCalledWith(3)
    expect(screen.queryByText('Faction Points')).toBeNull()
    expect(screen.getByText('Players')).toBeTruthy()
  })

  it('without the param keeps the faction race and asks for no era', async () => {
    at('/leaderboard')
    expect(await screen.findByText('Faction Points')).toBeTruthy()
    expect(mocks.getLeaderboard).toHaveBeenCalledWith({ limit: 500, era: undefined })
    expect(mocks.getLeaderboardEra).not.toHaveBeenCalled()
  })
})
