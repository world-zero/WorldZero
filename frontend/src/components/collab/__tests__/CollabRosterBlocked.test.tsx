// @vitest-environment jsdom
/** #4027 — a blocked member gets no per-row nudge and is not counted for the crew nudge. */
import { render, screen, cleanup, waitFor } from '@testing-library/react'
import { describe, it, expect, afterEach, vi } from 'vitest'

const h = vi.hoisted(() => ({ listBlocks: vi.fn() }))

vi.mock('../../../auth/AuthContext', async (orig) => ({
  ...(await orig<typeof import('../../../auth/AuthContext')>()),
  useAuth: () => ({ user: { character: { id: 1 } } }),
}))
vi.mock('../../../api/relationships', () => ({ listBlocks: h.listBlocks }))

import '../../../i18n'
import type { PraxisMemberOut } from '../../../api/praxis'
import { CollabRoster } from '../CollabRoster'
import { collabCopy } from '../collabCopy'

const member = (id: number, cast: boolean): PraxisMemberOut => ({
  id,
  praxis_id: 1,
  character_id: id,
  character_display_name: `M${id}`,
  character_avatar_url: '',
  has_approved: cast,
  is_done: false,
  joined_at: '2026-01-01T00:00:00Z',
  nudged_at: null,
  nudge_again_at: null,
  approved_at: null,
})

const mount = () =>
  render(
    <CollabRoster
      praxisType="collab"
      members={[member(1, true), member(2, false), member(3, false)]}
      currentCharacterId={1}
      factionSlug={null}
      onNudge={() => {}}
      onNudgeCrew={() => {}}
    />,
  )

const rowNudge = (name: string) =>
  screen.queryByLabelText(collabCopy(null, 'nudgeAria', { name, time: '' }))
const crewNudge = () => screen.queryByText(collabCopy(null, 'nudgeCrewAction'))

afterEach(() => {
  cleanup()
  h.listBlocks.mockReset()
})

describe('CollabRoster reach controls', () => {
  it('shows both nudges when nobody is blocked', async () => {
    h.listBlocks.mockResolvedValue([])
    mount()
    await waitFor(() => expect(h.listBlocks).toHaveBeenCalled())
    expect(rowNudge('M3')).not.toBeNull()
    expect(crewNudge()).not.toBeNull()
  })

  it('drops the blocked member from the row nudge and the crew count', async () => {
    h.listBlocks.mockResolvedValue([{ character_id: 3 }])
    mount()
    await waitFor(() => expect(rowNudge('M3')).toBeNull())
    expect(rowNudge('M2')).not.toBeNull()
    expect(crewNudge()).toBeNull()
  })
})
