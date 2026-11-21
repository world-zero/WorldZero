// @vitest-environment jsdom
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'

import '../i18n'
import Contact from '../pages/Contact'

const apiPost = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({ apiPost }))

describe('Contact honeypot', () => {
  it('keeps the trap hidden from screen readers and the keyboard', () => {
    const { container } = render(
      <MemoryRouter>
        <Contact />
      </MemoryRouter>,
    )
    const trap = container.querySelector('[aria-hidden="true"] input[name="website"]')
    expect(trap).not.toBeNull()
    expect(trap).toHaveProperty('tabIndex', -1)
  })

  it('still submits with an empty website and shows success', async () => {
    apiPost.mockResolvedValue({})
    const { container } = render(
      <MemoryRouter>
        <Contact />
      </MemoryRouter>,
    )
    const field = (n: string) => container.querySelector(`[name="${n}"]`) as HTMLElement
    fireEvent.change(field('name'), { target: { value: 'Ada' } })
    fireEvent.change(field('email'), { target: { value: 'ada@example.com' } })
    fireEvent.change(field('message'), { target: { value: 'hello' } })
    fireEvent.submit(container.querySelector('form') as HTMLFormElement)

    await screen.findByText('Message sent!')
    expect(apiPost).toHaveBeenCalledWith('/contact', {
      body: { name: 'Ada', email: 'ada@example.com', message: 'hello', website: '' },
    })
  })
})
