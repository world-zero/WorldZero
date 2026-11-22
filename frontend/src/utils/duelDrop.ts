/** States a duel can't be dissolved from (Q5), so its side can't be dropped. */
export const DUEL_STATES_THAT_BLOCK_DROP: ReadonlySet<string> = new Set([
  "awaiting_honest_side",
  "live",
  "live_forfeited",
  "resolved",
  "no_contest",
]);
