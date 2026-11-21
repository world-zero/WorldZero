import type { ReactNode } from 'react'
import { useModal } from '../../hooks/useModal'
import { drawAtRoot } from './drawAtRoot'
import './bottomSheet.css'

/**
 * The one phone bottom-sheet chassis: scrim button, panel, optional grab handle,
 * drawn at the root through `drawAtRoot`. Default paint is the You sheet's; a
 * sheet with its own look passes `panelClass`.
 */
export default function BottomSheet({
  label,
  scrimLabel,
  onClose,
  aboveTabBar = false,
  grab = true,
  panelClass = '',
  children,
}: {
  label: string
  scrimLabel: string
  onClose: () => void
  /** Stop above the tab bar, which stays live, instead of covering it. */
  aboveTabBar?: boolean
  grab?: boolean
  panelClass?: string
  children: ReactNode
}) {
  const ref = useModal(onClose)
  return drawAtRoot(
    <div
      ref={ref}
      role="dialog"
      aria-modal="true"
      aria-label={label}
      className={aboveTabBar ? 'sheet-above-tabs' : undefined}
    >
      <button type="button" tabIndex={-1} className="sheet-scrim" aria-label={scrimLabel} onClick={onClose} />
      <div className={`sheet-panel ${panelClass}`}>
        {grab && <span className="sheet-grab" />}
        {children}
      </div>
    </div>,
  )
}
