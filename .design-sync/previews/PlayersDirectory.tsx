// PlayersDirectory — the Players page (#1855): podium, faction
// race, roster. Phone layout comes from `useFormFactor()`, not a second card;
// it takes the shared fixture.
//
// Pure presentational skin — it takes the whole page as controlled props and
// fetches nothing, so this card is the real surface, not an empty state.
//
// ONE CELL: `scoreMode` is the one prop that varies the view, and it is a
// control the card renders — a second cell would be the same page with one
// segment pressed.
import { PlayersDirectory } from 'worldzero-frontend'
import { playersProps } from './_state'

export function Roster() {
  return <PlayersDirectory {...playersProps} />
}
