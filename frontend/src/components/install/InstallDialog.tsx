import type { ReactNode } from 'react'
import { useModal } from '../../hooks/useModal'
import { drawAtRoot } from '../ui/drawAtRoot'
import './installAsk.css'

/** A full-screen wisp layer: focus-trapped like every dialog, drawn at the root. */
export default function InstallDialog({
  labelledBy,
  className,
  children,
}: {
  readonly labelledBy: string
  readonly className: string
  readonly children: ReactNode
}) {
  const ref = useModal()
  return drawAtRoot(
    <div ref={ref} role="dialog" aria-labelledby={labelledBy} className={className}>
      {children}
    </div>,
  )
}
