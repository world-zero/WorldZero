// @vitest-environment jsdom
/** #3772 — a profile's ?mode=&with=<id> lands with that player staged, then leaves the URL. */
import { act, cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '../../../i18n'

import { aCharacter, aPraxis } from '../../../test/fixtures'

vi.mock('../../../auth/AuthContext', () => ({
  useAuth: () => ({ user: { character: { id: 3 } }, loading: false, refetch: async () => {} }),
}))
vi.mock('../../../hooks/useGameConfig', () => ({ useGameConfig: () => null }))
vi.mock('../../../api/metatasks', () => ({ listMetatasks: vi.fn(async () => []) }))
vi.mock('../../../api/relationships', () => ({
  listBlocks: vi.fn(async () => []),
  listRelationships: vi.fn(async () => []),
}))
vi.mock('../../../api/tasks', () => ({ getTask: vi.fn(async () => null) }))
vi.mock('../../../api/characters', async (orig) => ({
  ...(await orig<typeof import('../../../api/characters')>()),
  getCharacter: vi.fn(async () => aCharacter({ id: 7, display_name: 'Reza' })),
  listCharacters: vi.fn(async () => []),
}))
const solo = aPraxis({ id: 1, type: 'solo', status: 'in_progress', duel_id: null })
const collab = { ...solo, type: 'collab' as const }
vi.mock('../../../api/praxis', async (orig) => ({
  ...(await orig<typeof import('../../../api/praxis')>()),
  takeJustCreatedPraxis: () => null,
  getPraxis: vi.fn(async () => solo),
  changePraxisType: vi.fn(async () => collab),
}))

import { useEditPraxis } from '../useEditPraxis'

function Probe() {
  const s = useEditPraxis('1')
  const { search } = useLocation()
  return (
    <p data-testid="out">
      {`${s.praxis?.type}|${s.duelMode}|${s.staged?.display_name ?? '-'}|${search}`}
    </p>
  )
}
const land = async (query: string) => {
  render(
    <MemoryRouter initialEntries={[`/praxis/1/edit${query}`]}>
      <Routes>
        <Route path="/praxis/:id/edit" element={<Probe />} />
      </Routes>
    </MemoryRouter>,
  )
  await act(async () => {})
  await act(async () => {})
  return screen.getByTestId('out').textContent
}
afterEach(cleanup)

describe('profile hand-off', () => {
  it('duel: opens the duel pane with the opponent staged, params cleared', async () => {
    expect(await land('?mode=duel&with=7')).toBe('solo|true|Reza|')
  })
  it('collab: flips to collab with the invitee staged, params cleared', async () => {
    expect(await land('?mode=collab&with=7')).toBe('collab|false|Reza|')
  })
})
