/**
 * A duel's figures and verdict sentence, shared by `DuelCard` and the
 * side-by-side reader (#1084). The callers differ only in side order (viewer's
 * `mine`/`rival` vs `challenger`/`opponent`), so order is an argument.
 */
import type { TFunction } from 'i18next'
import type { DuelDetailOut, DuelSideOut } from '../../api/duel'
import { formatPoints } from '../../utils/points'

export const NO_SCORE = '—'

function finalFor(duel: DuelDetailOut, side: DuelSideOut): number | null {
  return side.character_id === duel.challenger.character_id
    ? duel.challenger_final_points
    : duel.opponent_final_points
}

export function hasForfeited(duel: DuelDetailOut, side: DuelSideOut): boolean {
  return (
    duel.forfeited_by_character_id != null &&
    side.character_id === duel.forfeited_by_character_id
  )
}

/**
 * Forfeit is checked before the frozen pair: it survives era close.
 * `formatPoints` to match `ScoreStamp`'s total on the same page (#1866).
 */
export function duelScoreFor(duel: DuelDetailOut, side: DuelSideOut): string {
  if (hasForfeited(duel, side)) return NO_SCORE
  if (duel.state === 'resolved' || duel.state === 'no_contest') {
    const frozen = finalFor(duel, side)
    return frozen != null ? formatPoints(frozen) : NO_SCORE
  }
  return formatPoints(side.points_from_votes)
}

/** One `duelCrossLink.*` string; `a`, `b` in the caller's reading order. */
export function duelVerdict(
  duel: DuelDetailOut,
  a: DuelSideOut,
  b: DuelSideOut,
  t: TFunction<'praxis'>,
): string {
  // Era close keeps a forfeit: RESOLVED with a forfeiter is still won by default.
  if (
    duel.state === 'live_forfeited' ||
    duel.state === 'awaiting_honest_side' ||
    (duel.state === 'resolved' && duel.forfeited_by_character_id != null)
  ) {
    return t('duelCrossLink.wonByDefault')
  }
  if (duel.state === 'no_contest') return t('duelCrossLink.finalNoContest')

  if (duel.state === 'resolved') {
    // Q10: no winner without votes, so 0-0 reads tied whatever the perk did.
    const noVotes = a.points_from_votes === 0 && b.points_from_votes === 0
    return t('duelCrossLink.final', {
      standing:
        duel.winner_character_id == null || noVotes
          ? t('duelCrossLink.finalStanding.tied')
          : t('duelCrossLink.finalStanding.won', {
              name:
                duel.winner_character_id === a.character_id
                  ? a.display_name
                  : b.display_name,
            }),
    })
  }

  const margin = a.points_from_votes - b.points_from_votes
  return t('duelCrossLink.live', {
    standing:
      margin === 0
        ? t('duelCrossLink.standing.tied')
        : t('duelCrossLink.standing.leads', {
            name: margin > 0 ? a.display_name : b.display_name,
            margin: formatPoints(Math.abs(margin)),
          }),
  })
}
