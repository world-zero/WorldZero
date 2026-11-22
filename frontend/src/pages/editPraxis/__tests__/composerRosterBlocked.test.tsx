// @vitest-environment jsdom
/** #4027 — invite and opponent search never offer someone the viewer blocked. */
import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

const h = vi.hoisted(() => ({ listBlocks: vi.fn(), listCharacters: vi.fn() }))

vi.mock('../../../auth/AuthContext', async (orig) => ({
  ...(await orig<typeof import('../../../auth/AuthContext')>()),
  useAuth: () => ({ user: { character: { id: 3 } } }),
}))
vi.mock('../../../api/relationships', () => ({
  listBlocks: h.listBlocks,
  listRelationships: vi.fn(async () => []),
}))
vi.mock('../../../api/characters', async (orig) => ({
  ...(await orig<typeof import('../../../api/characters')>()),
  listCharacters: h.listCharacters,
}))

import { aCharacter, aPraxis } from '../../../test/fixtures'
import { useComposerRoster } from '../useComposerRoster'

// Stable references: the search effect keys on `praxis`, so a fresh one per render loops.
const PRAXIS = aPraxis({ id: 3, type: 'collab', duel_id: null })
const PANES = { closed: { duel: null, paneOpen: false }, open: { duel: null, paneOpen: true } }

const search = async (paneOpen: boolean) => {
  h.listBlocks.mockResolvedValue([{ character_id: 9 }])
  h.listCharacters.mockResolvedValue([
    aCharacter({ id: 9, display_name: 'Blocked' }),
    aCharacter({ id: 10, display_name: 'Fine' }),
  ])
  const { result } = renderHook(() =>
    useComposerRoster({ praxis: PRAXIS, duelPane: paneOpen ? PANES.open : PANES.closed }),
  )
  await waitFor(() => expect(h.listBlocks).toHaveBeenCalled())
  await act(async () => {
    await Promise.resolve()
  })
  act(() => result.current.setInviteQuery('wr'))
  await waitFor(() => expect(result.current.inviteResults.length).toBeGreaterThan(0))
  return result.current.inviteResults.map((c) => c.id)
}

describe('useComposerRoster search', () => {
  it('omits a blocked character from collab invitees', async () => {
    expect(await search(false)).toEqual([10])
  })

  it('omits a blocked character from opponent search', async () => {
    expect(await search(true)).toEqual([10])
  })
})

describe('useComposerRoster staged player', () => {
  const stagedFor = async (praxis: typeof PRAXIS, who: number) => {
    h.listBlocks.mockResolvedValue([{ character_id: 9 }])
    const { result } = renderHook(() => useComposerRoster({ praxis, duelPane: PANES.closed }))
    await waitFor(() => expect(h.listBlocks).toHaveBeenCalled())
    await act(async () => {
      await Promise.resolve()
    })
    act(() => result.current.setStaged(aCharacter({ id: who })))
    return result.current.staged
  }
  const withMember = aPraxis({
    id: 4,
    type: 'collab',
    duel_id: null,
    members: [{ character_id: 11 }] as never,
  })

  it('stages an eligible player', async () => {
    expect((await stagedFor(PRAXIS, 10))?.id).toBe(10)
  })
  it.each([
    ['a blocked', PRAXIS, 9],
    ['the viewer', PRAXIS, 3],
    ['an existing member', withMember, 11],
  ])('never stages %s character', async (_n, praxis, who) => {
    expect(await stagedFor(praxis, who)).toBeNull()
  })
})
