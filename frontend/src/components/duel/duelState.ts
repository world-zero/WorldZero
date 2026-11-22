/** Mirrors `backend/services/duel_state.py` ALLOWED_FROM; keep in step with it. */
import type { DuelDetailOut } from '../../api/duel'

export type DuelState = DuelDetailOut['state']
type DuelStateLike = Pick<DuelDetailOut, 'state'> | null | undefined

type Action = 'accept' | 'decline' | 'dissolve' | 'cast' | 'reopen'

const ALLOWED_FROM: Record<Action, readonly DuelState[]> = {
  accept: ['challenged'],
  decline: ['challenged'],
  dissolve: ['challenged', 'drafting', 'one_cast'],
  cast: ['drafting', 'one_cast', 'awaiting_honest_side', 'live', 'live_forfeited'],
  reopen: ['challenged', 'dissolved', 'one_cast', 'awaiting_honest_side', 'live'],
}

const PRE_LIVE: readonly DuelState[] = [
  'challenged',
  'drafting',
  'one_cast',
  'awaiting_honest_side',
]

// A null duel (detail still loading) allows nothing.
export function duelCan(action: Action, duel: DuelStateLike): boolean {
  return duel != null && ALLOWED_FROM[action].includes(duel.state)
}

export function duelPreLive(duel: DuelStateLike): boolean {
  return duel != null && PRE_LIVE.includes(duel.state)
}

export function duelAccepted(duel: DuelStateLike): boolean {
  return duel != null && duel.state !== 'challenged' && duel.state !== 'dissolved'
}

export function duelOutcomeReadable(duel: DuelStateLike): boolean {
  return duel != null && !duelPreLive(duel) && duel.state !== 'dissolved'
}

export function duelCanDrop(duel: DuelStateLike): boolean {
  return duel == null || duelCan('dissolve', duel) || duel.state === 'dissolved'
}
