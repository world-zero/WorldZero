import { useLayoutEffect, type RefObject } from 'react'

/** Measures each `.spectrum-rule`'s x in the sheet (#4113) so `.spectrum-shared` can share one
 *  gradient space. Not `background-attachment: fixed`: it repaints on scroll and iOS ignores it. */
export function useSharedSpectrum(anchor: RefObject<HTMLElement | null>): void {
  useLayoutEffect(() => {
    const sheet = anchor.current?.parentElement
    if (!sheet) return
    const sync = () => {
      const left = sheet.getBoundingClientRect().left + sheet.clientLeft
      sheet.style.setProperty('--spec-w', `${sheet.clientWidth}px`)
      sheet.querySelectorAll<HTMLElement>('.spectrum-rule').forEach((el) => {
        el.style.setProperty('--spec-x', `${el.getBoundingClientRect().left - left}px`)
      })
    }
    sync()
    const ro = new ResizeObserver(sync)
    ro.observe(sheet)
    const mo = new MutationObserver(sync)
    mo.observe(sheet, { childList: true, subtree: true })
    return () => {
      ro.disconnect()
      mo.disconnect()
    }
  })
}
