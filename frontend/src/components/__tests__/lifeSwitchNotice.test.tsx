// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import '../../i18n'
import LifeSwitchNotice from '../LifeSwitchNotice'

let user: { character: { id: number; display_name: string } }
const getMyCharacters = vi.fn()

vi.mock('../../auth/AuthContext', () => ({ useAuth: () => ({ user }) }))
vi.mock('../../api/me', () => ({ getMyCharacters: () => getMyCharacters() }))

describe('LifeSwitchNotice (#4238 S8)', () => {
  beforeEach(() => {
    user = { character: { id: 1, display_name: 'Old' } }
    getMyCharacters.mockReset()
  })

  it('says who you are now playing as when the carried life left the roster', async () => {
    const { rerender } = render(<LifeSwitchNotice />)
    user = { character: { id: 2, display_name: 'Sibling' } }
    getMyCharacters.mockResolvedValue([{ id: 2 }])
    rerender(<LifeSwitchNotice />)
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain("You're now playing as Sibling."))
  })

  it('stays quiet when the old life is still on the roster (a plain switch)', async () => {
    const { rerender } = render(<LifeSwitchNotice />)
    user = { character: { id: 2, display_name: 'Sibling' } }
    getMyCharacters.mockResolvedValue([{ id: 1 }, { id: 2 }])
    rerender(<LifeSwitchNotice />)
    await waitFor(() => expect(getMyCharacters).toHaveBeenCalled())
    expect(screen.queryByRole('status')).toBeNull()
  })
})
