import PlayersDirectory from '../PlayersDirectory'
import type { PlayersViewProps } from '../playersData'
import { ff } from './formFactorMock'

/** The one page at each form factor; the test file must `vi.mock` useFormFactor with `mockModule`. */
export const DesktopPlayers = (p: PlayersViewProps) => {
  ff.current = 'desktop'
  return <PlayersDirectory {...p} />
}
export const MobilePlayers = (p: PlayersViewProps) => {
  ff.current = 'mobile'
  return <PlayersDirectory {...p} />
}
