# ADR-0100 — A Rival duel's winner takes a flat era bonus, fixed at accept

**Status:** Accepted
**Date:** 2026-11-21

**Relates to:** ADR-0011 (duels), ADR-0052 (duel outcome is final at era close),
ADR-0077 (blocks stay narrow), ADR-0086 (only base points multiply), #3858

## Decision

- When a duel is accepted (`pending` → `active`) and **both** foe edges exist between the
  pair (display status *Rivals*), `duel.rival_bonus` is set true. One-sided Foe, Targeted
  and Tsundere do not qualify.
- Whoever `duel_winner` names — the sole tie-taker on a tie, the foe on a forfeit — gets
  `era.rival_duel_bonus` flat points, added after `task_points × faction × duel`. A true
  tie pays nobody. The bonus is never part of the winner comparison, which stays on
  `points_from_votes`.
- It is an ordinary praxis term: it reaches score, faction standings, levels and taunts
  through `compute_owner_contributions`, and floats with the lead until era close.
- The value is an era rule on `EraConfig`, not a faction perk.

## Why snapshot at accept

Edges are free to add and delete. Reading them live would let either player switch the
bonus on or off mid-duel by unfoeing, which turns a relationship into a scoring lever.
Accept is the moment both players have agreed to the fight, so the pair's standing then is
the one that counts. A later Block doesn't void it either: blocks hide, they don't re-score
(ADR-0077).
