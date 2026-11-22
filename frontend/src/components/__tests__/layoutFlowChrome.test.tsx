// @vitest-environment jsdom
/** Seam: `Layout` + `useHidePhoneChrome` (#3753): the phone tab bar is absent while the flow shows to a signed-out visitor, back after it or once signed in. */
import { useState, type ReactNode } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import '../../i18n'
import { AuthContext } from '../../auth/AuthContext'
import Onboarding from '../../pages/Onboarding'
import Layout from '../Layout'

const form = vi.hoisted(() => ({ current: 'mobile' }))
vi.mock('../../hooks/useFormFactor', () => ({ useFormFactor: () => form.current }))
vi.mock('../backdrop/BackdropContext', () => ({ BackdropProvider: ({ children }: { children: ReactNode }) => children }))
vi.mock('../backdrop/FactionBackdrop', () => ({ default: () => null }))
vi.mock('../LevelUpWatcher', () => ({ default: () => null }))
vi.mock('../InvitationWatcher', () => ({ default: () => null }))
vi.mock('../NavBar', () => ({ default: () => <nav data-testid="top-nav" /> }))
vi.mock('../layout/MobileTabBar', () => ({ default: () => <nav data-testid="tab-bar" /> }))
vi.mock('../../pages/onboarding/OnboardingFlow', () => ({ default: () => null }))
vi.mock('../layout/Sidebar', () => ({ default: () => null, panelStyle: {} }))

function Page() {
  const [inFlow, setInFlow] = useState(true)
  return (
    <>
      <button onClick={() => setInFlow(false)}>arrive</button>
      {inFlow && <Onboarding />}
    </>
  )
}
function renderApp(user: unknown = null) {
  window.scrollTo = () => {}
  render(
    <MemoryRouter initialEntries={['/start']}>
      <AuthContext.Provider value={{ user: user as never, loading: false, refetch: async () => {}, applyUser: () => {}, signOut: async () => {} }}>
        <Layout><Page /></Layout>
      </AuthContext.Provider>
    </MemoryRouter>,
  )
}
afterEach(cleanup)

describe('phone chrome during the onboarding flow', () => {
  it('hides the tab bar mid-flow and restores it on arrival', () => {
    form.current = 'mobile'
    renderApp()
    expect(screen.queryByTestId('tab-bar')).toBeNull()
    const footer = document.querySelector('footer')!
    expect(footer.closest<HTMLElement>('[style]')!.style.getPropertyValue('--tab-bar-clearance')).toBe('env(safe-area-inset-bottom)')
    fireEvent.click(screen.getByText('arrive'))
    expect(screen.getByTestId('tab-bar')).toBeTruthy()
  })

  it('signed in with no character on /start keeps the tab bar and its clearance', () => {
    form.current = 'mobile'
    renderApp({ id: 1, character: null, has_accepted_terms: false })
    expect(screen.getByTestId('tab-bar')).toBeTruthy()
    expect(document.querySelector('[style*="--tab-bar-clearance"]')).toBeNull()
  })

  it('desktop keeps its top nav mid-flow', () => {
    form.current = 'desktop'
    renderApp()
    expect(screen.getByTestId('top-nav')).toBeTruthy()
  })
})
