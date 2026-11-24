import { useRef, type PointerEvent, type ReactNode } from 'react'
import { useModal } from '../../hooks/useModal'
import { drawAtRoot } from './drawAtRoot'
import './bottomSheet.css'

/** How far the grab handle must be pulled down before letting go closes the sheet. */
const DISMISS_DRAG_PX = 80

/**
 * The one phone bottom-sheet chassis: scrim button, panel, optional grab handle,
 * drawn at the root through `drawAtRoot`. Default paint is the You sheet's; a
 * sheet with its own look passes `panelClass`. Pulling the handle down closes it (#4292).
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
  const panel = useRef<HTMLDivElement>(null)
  const dragFrom = useRef<number | null>(null)

  // The panel follows the finger by a direct style write: per-frame, so not state.
  const follow = (dy: number) => {
    if (panel.current) panel.current.style.transform = dy > 0 ? `translateY(${dy}px)` : ''
  }
  const onDown = (event: PointerEvent<HTMLSpanElement>) => {
    dragFrom.current = event.clientY
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }
  const onMove = (event: PointerEvent<HTMLSpanElement>) => {
    if (dragFrom.current !== null) follow(event.clientY - dragFrom.current)
  }
  const onUp = (event: PointerEvent<HTMLSpanElement>) => {
    if (dragFrom.current === null) return
    const dy = event.clientY - dragFrom.current
    dragFrom.current = null
    follow(0)
    if (dy > DISMISS_DRAG_PX) onClose()
  }
  const onCancel = () => {
    dragFrom.current = null
    follow(0)
  }

  return drawAtRoot(
    <div
      ref={ref}
      role="dialog"
      aria-modal="true"
      aria-label={label}
      className={aboveTabBar ? 'sheet-above-tabs' : undefined}
    >
      <button type="button" tabIndex={-1} className="sheet-scrim" aria-label={scrimLabel} onClick={onClose} />
      <div ref={panel} className={`sheet-panel ${panelClass}`}>
        {grab && (
          <span
            className="sheet-grab"
            onPointerDown={onDown}
            onPointerMove={onMove}
            onPointerUp={onUp}
            onPointerCancel={onCancel}
          />
        )}
        {children}
      </div>
    </div>,
  )
}
