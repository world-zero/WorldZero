// @vitest-environment jsdom
/** Seam: MessagesTab over a mocked admin API; long unbroken sender text must wrap, not widen the page. */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '../../../i18n'
import MessagesTab from '../MessagesTab'

const api = vi.hoisted(() => ({ getMessages: vi.fn(), archiveMessage: vi.fn() }))
vi.mock('../../../api/admin', () => api)
vi.mock('../useAdminCounts', () => ({ useReloadCounts: () => vi.fn() }))

afterEach(cleanup)

describe('MessagesTab wrapping', () => {
  it('wraps name, email and message anywhere and lets the column shrink', async () => {
    api.getMessages.mockResolvedValue([{
      id: 1, name: 'N'.repeat(100), email: `${'e'.repeat(250)}@x.org`,
      message: 'M'.repeat(3000), is_archived: false, created_at: new Date().toISOString(),
    }])
    render(<MessagesTab />)
    const name = await screen.findByText('N'.repeat(100))
    const email = screen.getByText(/e{250}@x\.org/)
    const message = screen.getByText('M'.repeat(3000))
    for (const el of [name, email, message]) expect(el.className).toContain('[overflow-wrap:anywhere]')
    expect(message.className).toContain('whitespace-pre-wrap')
    expect(name.parentElement!.className).toContain('min-w-0')
  })
})
