// @vitest-environment jsdom
/** #4027 — the rival nudge on a duel's waiting surface is hidden once the viewer blocks the rival. */
import { render, screen, cleanup, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const h = vi.hoisted(() => ({ listBlocks: vi.fn() }))

vi.mock('../../../../auth/AuthContext', async (orig) => ({
  ...(await orig<typeof import('../../../../auth/AuthContext')>()),
  useAuth: () => ({ user: { character: { id: 3 } } }),
}))
vi.mock('../../../../api/relationships', () => ({ listBlocks: h.listBlocks }))

import '../../../../i18n'
import { collabCopy } from '../../../../components/collab/collabCopy'
import { aDuel, aDuelSide, aPraxis, anEditPraxisState } from '../../../../test/fixtures'
import { DEFAULT_COMPOSER_DRESS } from '../../archetypes/DefaultEditPraxis'
import PraxisWaitingSurface from '../PraxisWaitingSurface'

const STATE = anEditPraxisState({
  currentCharacterId: 3,
  praxis: aPraxis({
    type: 'solo',
    status: 'submitted',
    duel_id: 5,
    members: [],
    invites: [],
    submit_proposed_at: null,
  }),
  duel: aDuel({
    status: 'active',
    challenger: aDuelSide({ character_id: 3, display_name: 'Wren' }),
    opponent: aDuelSide({ praxis_id: null, character_id: 4, display_name: 'Rax', is_submitted: false }),
  }),
})

const mount = () =>
  render(
    <MemoryRouter>
      <PraxisWaitingSurface {...STATE} dress={DEFAULT_COMPOSER_DRESS} />
    </MemoryRouter>,
  )

const rivalNudge = () =>
  screen.queryByLabelText(collabCopy('na', 'duelNudgeAria', { name: 'Rax', time: '' }))

beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
})

afterEach(() => {
  cleanup()
  h.listBlocks.mockReset()
})

describe('PraxisWaitingSurface rival nudge', () => {
  it('is offered when the rival is not blocked', async () => {
    h.listBlocks.mockResolvedValue([])
    mount()
    await waitFor(() => expect(h.listBlocks).toHaveBeenCalled())
    expect(rivalNudge()).not.toBeNull()
  })

  it('is hidden when the viewer blocked the rival', async () => {
    h.listBlocks.mockResolvedValue([{ character_id: 4 }])
    mount()
    await waitFor(() => expect(rivalNudge()).toBeNull())
  })
})
