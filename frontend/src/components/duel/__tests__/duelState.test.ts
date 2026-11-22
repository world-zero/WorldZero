import { describe, expect, it } from 'vitest'
import type { TFunction } from 'i18next'
import { aDuel, aDuelSide } from '../../../test/fixtures'
import { duelAccepted, duelCan, duelCanDrop, duelPreLive } from '../duelState'
import { duelVerdict } from '../standing'

const t = ((key: string, opts?: { standing?: string }) =>
  opts?.standing ? `${key}:${opts.standing}` : key) as unknown as TFunction<'praxis'>

describe('duelState rules', () => {
  it('offers accept and decline only while challenged', () => {
    expect(duelCan('accept', aDuel({ state: 'challenged' }))).toBe(true)
    expect(duelCan('accept', aDuel({ state: 'dissolved' }))).toBe(false)
    expect(duelCan('decline', aDuel({ state: 'live' }))).toBe(false)
  })

  it('never dissolves or drops a forfeit state', () => {
    for (const state of ['awaiting_honest_side', 'live_forfeited', 'live'] as const) {
      expect(duelCan('dissolve', aDuel({ state }))).toBe(false)
      expect(duelCanDrop(aDuel({ state }))).toBe(false)
    }
    expect(duelCanDrop(aDuel({ state: 'dissolved' }))).toBe(true)
  })

  it('reads a reopened live side as accepted, not challenged', () => {
    expect(duelAccepted(aDuel({ state: 'live' }))).toBe(true)
    expect(duelAccepted(aDuel({ state: 'challenged' }))).toBe(false)
    expect(duelPreLive(aDuel({ state: 'live' }))).toBe(false)
  })
})

describe('duelVerdict (Q10)', () => {
  const a = aDuelSide({ character_id: 1, display_name: 'Ada', points_from_votes: 0 })
  const b = aDuelSide({ character_id: 2, display_name: 'Rax', points_from_votes: 0 })

  it('reads a 0-vote result as tied even when a winner was stamped', () => {
    const duel = aDuel({ state: 'resolved', status: 'resolved', winner_character_id: 2 })
    expect(duelVerdict(duel, a, b, t)).toContain('tied')
  })

  it('keeps a forfeit win at 0 votes, and no contest apart', () => {
    expect(duelVerdict(aDuel({ state: 'live_forfeited' }), a, b, t)).toBe(
      'duelCrossLink.wonByDefault',
    )
    expect(duelVerdict(aDuel({ state: 'no_contest', status: 'resolved' }), a, b, t)).toBe(
      'duelCrossLink.finalNoContest',
    )
  })
})
