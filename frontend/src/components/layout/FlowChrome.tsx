import { createContext, useContext, useLayoutEffect } from 'react'

/** Set by `Layout`; the onboarding flow raises it while mounted and `active` so the phone chrome steps aside. */
export const FlowChromeContext = createContext<(on: boolean) => void>(() => {})

export function useHidePhoneChrome(active: boolean): void {
  const set = useContext(FlowChromeContext)
  useLayoutEffect(() => {
    set(active)
    return () => set(false)
  }, [set, active])
}
