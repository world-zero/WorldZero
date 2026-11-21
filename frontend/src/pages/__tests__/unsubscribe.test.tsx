// @vitest-environment jsdom
/** #2164 — `/unsubscribe`: the opened link turns its event off, a second click turns all off. */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  one: vi.fn(),
  all: vi.fn(),
}))

vi.mock('../../api/email', () => ({ unsubscribeEmail: api.one, unsubscribeAllEmail: api.all }))

import '../../i18n'
import Unsubscribe from '../Unsubscribe'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function open(token: string) {
  render(
    <MemoryRouter initialEntries={[`/unsubscribe?token=${token}`]}>
      <Unsubscribe />
    </MemoryRouter>,
  )
}

describe('the unsubscribe page', () => {
  it('turns the mail\'s event off on arrival, naming it, then offers turn-them-all-off', async () => {
    api.one.mockResolvedValue('comment_on_mine')
    api.all.mockResolvedValue(undefined)
    open('abc')
    expect(await screen.findByText(/Comments on my praxis/)).toBeTruthy()
    expect(api.one).toHaveBeenCalledWith('abc')
    fireEvent.click(screen.getByRole('button'))
    expect(await screen.findByText(/any notification email/)).toBeTruthy()
    expect(api.all).toHaveBeenCalledWith('abc')
  })

  it('shows a plain error for a bad token and no turn-off button', async () => {
    api.one.mockRejectedValue(new Error('400'))
    open('forged')
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })
})
