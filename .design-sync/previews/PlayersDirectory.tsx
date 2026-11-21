// The Players page: controlled props, fetches nothing. One cell: scoreMode is a control the card renders.
import { PlayersDirectory } from 'worldzero-frontend'
import { playersProps } from './_state'

export function Roster() {
  return <PlayersDirectory {...playersProps} />
}
