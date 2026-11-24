import type { ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router-dom'
import type { components } from '../api/generated/schema'
import { playerLabel } from '../utils/playerLabel'

export type NameState = components['schemas']['NameState']

/** What every surface shows for a player's name (#4238): the name, "Name (Suspended)", or the placeholder. */
export function usePlayerLabel(): (name: string, state: NameState) => string {
  return playerLabel
}

/** A link to a player's profile, or plain text when there is no profile to open. */
export function PlayerLink({
  state,
  name,
  children,
  ...linkProps
}: LinkProps & { state: NameState; name?: string; children?: ReactNode }) {
  const label = usePlayerLabel()
  children = name === undefined ? children : label(name, state)
  if (state === 'ok') return <Link {...linkProps}>{children}</Link>
  const { to: _to, className, style, ...rest } = linkProps
  return (
    <span className={className} style={style} data-name-state={state} {...(rest as object)}>
      {children}
    </span>
  )
}
