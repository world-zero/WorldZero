// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '../../../i18n'
import { aPraxisCard } from '../../../test/fixtures'

const listPraxes = vi.hoisted(() => vi.fn())
vi.mock('../../../api/praxis', async (orig) => ({
  ...(await orig<typeof import('../../../api/praxis')>()),
  listPraxes,
}))

import ChallengeInviteButtons from '../ChallengeInviteButtons'

const Where = () => {
  const l = useLocation()
  return <p>{`AT ${l.pathname}${l.search}`}</p>
}
const mount = (over: Partial<React.ComponentProps<typeof ChallengeInviteButtons>> = {}) =>
  render(
    <MemoryRouter>
      <Routes>
        <Route
          path="/"
          element={
            <ChallengeInviteButtons
              viewerCharacterId={3}
              targetCharacterId={7}
              blocked={false}
              viewerLevel={5}
              duelLevelRequired={2}
              collabLevelRequired={1}
              targetDisplayName="Reza"
              factionSlug="coven"
              {...over}
            />
          }
        />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  )
afterEach(() => {
  cleanup()
  listPraxes.mockReset()
})

describe('visibility', () => {
  it('hides both on your own profile and on a blocked player', () => {
    mount({ targetCharacterId: 3 })
    expect(screen.queryByText('Challenge')).toBeNull()
    expect(screen.queryByText('Invite')).toBeNull()
    cleanup()
    mount({ blocked: true })
    expect(screen.queryByText('Challenge')).toBeNull()
    expect(screen.queryByText('Invite')).toBeNull()
  })
})

describe('level gates', () => {
  it('hides Challenge below the duel level and Invite below the collab level', () => {
    mount({ viewerLevel: 1, collabLevelRequired: 2 })
    expect(screen.queryByText('Challenge')).toBeNull()
    expect(screen.queryByText('Invite')).toBeNull()
  })
  it('shows both at or above the gates', () => {
    mount()
    expect(screen.getByText('Challenge')).toBeTruthy()
    expect(screen.getByText('Invite')).toBeTruthy()
  })
})

describe('the sheet', () => {
  it('Challenge lists solo in-progress praxes only, and a pick lands in the Duel composer', async () => {
    listPraxes.mockResolvedValue([
      aPraxisCard({ id: 1, title: 'Solo one', type: 'solo', status: 'in_progress', duel_id: null }),
      aPraxisCard({ id: 2, title: 'Collab one', type: 'collab', status: 'in_progress', duel_id: null }),
      aPraxisCard({ id: 3, title: 'Dueling', type: 'solo', status: 'in_progress', duel_id: 9 }),
      aPraxisCard({ id: 4, title: 'Done', type: 'solo', status: 'submitted', duel_id: null }),
    ])
    mount()
    fireEvent.click(screen.getByText('Challenge'))
    expect(await screen.findByText('Solo one')).toBeTruthy()
    expect(screen.queryByText('Collab one')).toBeNull()
    expect(screen.queryByText('Dueling')).toBeNull()
    expect(screen.queryByText('Done')).toBeNull()
    fireEvent.click(screen.getByText('Solo one'))
    expect(await screen.findByText('AT /praxis/1/edit?mode=duel&with=7')).toBeTruthy()
  })

  it('Invite lands on the Collab tab', async () => {
    listPraxes.mockResolvedValue([
      aPraxisCard({ id: 2, title: 'Collab one', type: 'collab', status: 'in_progress', duel_id: null }),
    ])
    mount()
    fireEvent.click(screen.getByText('Invite'))
    fireEvent.click(await screen.findByText('Collab one'))
    expect(await screen.findByText('AT /praxis/2/edit?mode=collab&with=7')).toBeTruthy()
  })

  it('says so and links to Tasks when nothing is eligible', async () => {
    listPraxes.mockResolvedValue([])
    mount()
    fireEvent.click(screen.getByText('Challenge'))
    const link = await screen.findByText('Browse Tasks')
    expect(link.getAttribute('href')).toBe('/tasks')
  })
})
