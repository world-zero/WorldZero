// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import '../../i18n'
import App from '../../App'
import SiteFooter from '../../components/layout/SiteFooter'

vi.mock('../AuthContext', () => ({
  useAuth: () => ({ user: null, loading: false }),
  hadSessionLastVisit: () => false,
}))
vi.mock('../AdminModeContext', () => ({ useAdminMode: () => ({ adminMode: false }) }))
vi.mock('../../components/Layout', () => ({ default: ({ children }: { children: React.ReactNode }) => children }))

const at = (path: string) =>
  render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)

describe('AI page replaces Donate (#4120, #4132)', () => {
  it('footer links AI and not Donate', () => {
    render(<MemoryRouter><SiteFooter /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'AI' }).getAttribute('href')).toBe('/ai')
    expect(screen.queryByText(/donate/i)).toBeNull()
  })

  it('/ai renders, signed out', async () => {
    at('/ai')
    expect(await screen.findByRole('heading', { name: 'Can I use AI in a Praxis?' })).toBeTruthy()
  })

  it('/donate is not found', async () => {
    at('/donate')
    expect(await screen.findByText(/not found/i)).toBeTruthy()
  })
})
