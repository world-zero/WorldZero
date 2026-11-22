// @vitest-environment jsdom
/** `?login` on /start and the failure notice on the step a failed sign-in resumes at. Seam: `Onboarding` page, router + auth context real. */
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import '../../i18n'
import { AuthContext } from '../../auth/AuthContext'
import type { CurrentUser } from '../../api/auth'
import { markOnboardingHandoff } from '../../utils/onboardingResume'
import home from '../../locales/en/home.json'
import Onboarding from '../Onboarding'

vi.mock('../../api/auth', () => ({ loginWith: () => {} }))

const USER = { account_id: 1, character: { id: 1 }, is_admin: false } as unknown as CurrentUser

const mount = (url: string, user: CurrentUser | null) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <AuthContext.Provider value={{ user, loading: false, refetch: async () => {}, applyUser: () => {}, signOut: async () => {} }}>
        <Onboarding />
      </AuthContext.Provider>
    </MemoryRouter>,
  )

beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }))
  const store = new Map<string, string>()
  vi.stubGlobal('sessionStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => store.set(k, v),
    removeItem: (k: string) => store.delete(k),
  })
  window.scrollTo = vi.fn()
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('/start?login', () => {
  it('opens the sign-in view for a guest', async () => {
    mount('/start?login', null)
    expect(await screen.findByTestId('onboarding-restart')).toBeTruthy()
  })

  it('stays on the title for a signed-in player', () => {
    mount('/start?login', USER)
    expect(screen.getByTestId('onboarding-start')).toBeTruthy()
    expect(screen.queryByTestId('onboarding-restart')).toBeNull()
  })

  it('shows the loginRequired copy for ?login=required', async () => {
    mount('/start?login=required', null)
    expect(await screen.findByText(home.loginRequired)).toBeTruthy()
  })
})

describe('a failed sign-in that resumes at the contract', () => {
  it('draws the failure notice above the terms card', async () => {
    markOnboardingHandoff()
    mount('/start?login=required', null)
    await screen.findByTestId('onboarding-accept-terms')
    expect(screen.getByText(home.loginRequired)).toBeTruthy()
  })
})
