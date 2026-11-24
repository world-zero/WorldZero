// @vitest-environment jsdom
/** The "Typo fixes waiting" list: accept all PUTs the shipped wording into each row. */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { putCopyOverride } from '../../../api/copy'
import i18n, { overriddenKeys } from '../../../i18n'
import CopyEditor, { shippedValue } from '../CopyEditor'

vi.mock('../../../api/copy', () => ({
  putCopyOverride: vi.fn(),
  deleteCopyOverride: vi.fn(),
}))

const NS = 'common'
const KEY = 'brand'

beforeEach(() => {
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }))
  vi.mocked(putCopyOverride).mockImplementation(async (o) => ({ ns: o.ns, key: o.key, value: o.value }))
})
afterEach(() => {
  vi.unstubAllGlobals()
  cleanup()
  i18n.addResource('en', NS, KEY, shippedValue(NS, KEY))
  overriddenKeys.delete(`${NS}:${KEY}`)
})

describe('Typo fixes waiting', () => {
  it('is hidden with no typo-class override', () => {
    render(<CopyEditor />)
    expect(screen.queryByText('Typo fixes waiting')).toBeNull()
  })

  it('accept all PUTs the shipped wording, then empties', async () => {
    i18n.addResource('en', NS, KEY, 'Wrold Zero')
    overriddenKeys.add(`${NS}:${KEY}`)
    render(<CopyEditor />)
    expect(screen.getByText('World').tagName).toBe('MARK')

    fireEvent.click(screen.getByText('accept all'))

    await waitFor(() => expect(screen.queryByText('Typo fixes waiting')).toBeNull())
    expect(putCopyOverride).toHaveBeenCalledWith({ ns: NS, key: KEY, value: 'World Zero', base: 'Wrold Zero' })
    expect(i18n.getResource('en', NS, KEY)).toBe('World Zero')
  })
})

describe('Typo fixes waiting, late arrivals', () => {
  it('shows a row whose override loads after mount', async () => {
    render(<CopyEditor />)
    expect(screen.queryByText('Typo fixes waiting')).toBeNull()
    i18n.addResource('en', NS, KEY, 'Wrold Zero')
    overriddenKeys.add(`${NS}:${KEY}`)
    await i18n.changeLanguage('en')
    await waitFor(() => expect(screen.getByText('Typo fixes waiting')).toBeTruthy())
  })
})
