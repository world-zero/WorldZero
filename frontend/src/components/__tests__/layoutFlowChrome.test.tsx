// @vitest-environment jsdom
/** Seam: `Layout` + `useHidePhoneChrome` (#3753): the phone tab bar is absent while the flow is mounted, back after it. */
import { useState, type ReactNode } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import '../../i18n'
import { AuthContext } from '../../auth/AuthContext'
import Layout from '../Layout'
import { useHidePhoneChrome } from '../layout/FlowChrome'

const form = vi.hoisted(() => ({ current: 'mobile' }))
vi.mock('../../hooks/useFormFactor', () => ({ useFormFactor: () => form.current }))
vi.mock('../backdrop/BackdropContext', () => ({ BackdropProvider: ({ children }: { children: ReactNode }) => children }))
vi.mock('../backdrop/FactionBackdrop', () => ({ default: () => null }))
vi.mock('../LevelUpWatcher', () => ({ default: () => null }))
vi.mock('../InvitationWatcher', () => ({ default: () => null }))
vi.mock('../NavBar', () => ({ default: () => <nav data-testid="top-nav" /> }))
vi.mock('../layout/MobileTabBar', () => ({ default: () => <nav data-testid="tab-bar" /> }))
vi.mock('../layout/Sidebar', () => ({ default: () => null, panelStyle: {} }))
vi.mock('../layout/SiteFooter', () => ({ default: () => null }))

function Flow() {
  useHidePhoneChrome()
  return null
}
function Page() {
  const [inFlow, setInFlow] = useState(true)
  return (
    <>
      <button onClick={() => setInFlow(false)}>arrive</button>
      {inFlow && <Flow />}
    </>
  )
}
function renderApp() {
  window.scrollTo = () => {}
  render(
    <MemoryRouter initialEntries={['/start']}>
      <AuthContext.Provider value={{ user: null, loading: false, refetch: async () => {}, applyUser: () => {}, signOut: async () => {} }}>
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
    fireEvent.click(screen.getByText('arrive'))
    expect(screen.getByTestId('tab-bar')).toBeTruthy()
  })

  it('desktop keeps its top nav mid-flow', () => {
    form.current = 'desktop'
    renderApp()
    expect(screen.getByTestId('top-nav')).toBeTruthy()
  })
})
