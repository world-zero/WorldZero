// @vitest-environment jsdom
/** #2164 — the email-pending line shows only while the server cannot send mail. */
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const harness = vi.hoisted(() => ({ emailAvailable: false }))

vi.mock('../../../api/client', () => ({
  apiGet: vi.fn(async () => ({
    data: {
      events: {},
      push_available: false,
      email_available: harness.emailAvailable,
      vapid_public_key: null,
    },
  })),
  apiPut: vi.fn(),
}))
vi.mock('../../../hooks/useFormFactor', () => ({ useFormFactor: () => 'desktop' }))

import '../../../i18n'
import NotificationsSection from '../sections/NotificationsSection'

afterEach(cleanup)

describe('the email-pending line', () => {
  it('shows when the server has no mail key', async () => {
    harness.emailAvailable = false
    render(<NotificationsSection sectionId="sec-notifications" />)
    expect(await screen.findByTestId('settings-notifications-email-pending')).toBeTruthy()
  })

  it('is gone once email is configured', async () => {
    harness.emailAvailable = true
    render(<NotificationsSection sectionId="sec-notifications" />)
    await vi.waitFor(() => expect(screen.queryByTestId('settings-notifications-status')).toBeNull())
    expect(screen.queryByTestId('settings-notifications-email-pending')).toBeNull()
  })
})
