import { createContext, useContext, useLayoutEffect } from 'react'

/** Set by `Layout`; the onboarding flow raises it while mounted so the phone chrome steps aside. */
export const FlowChromeContext = createContext<(on: boolean) => void>(() => {})

export function useHidePhoneChrome(): void {
  const set = useContext(FlowChromeContext)
  useLayoutEffect(() => {
    set(true)
    return () => set(false)
  }, [set])
}
