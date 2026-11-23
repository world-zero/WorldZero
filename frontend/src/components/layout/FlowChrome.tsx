import { createContext, useContext, useLayoutEffect } from 'react'

/** Set by `Layout`; the onboarding flow raises it while mounted. `Layout` decides what steps aside: the region's padding and the desktop sidebar always, the phone tab bar only for a signed-out visitor. */
export const FlowChromeContext = createContext<(on: boolean) => void>(() => {})

export function useFlowChrome(): void {
  const set = useContext(FlowChromeContext)
  useLayoutEffect(() => {
    set(true)
    return () => set(false)
  }, [set])
}
