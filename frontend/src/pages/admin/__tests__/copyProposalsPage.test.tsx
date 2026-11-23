// @vitest-environment jsdom
/** The copy proposals page: approve, reject, approve all, the 409 path and the delete line. */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../../../api/apiError'
import { listCopyProposals, settleCopyProposalLine, type CopyProposal } from '../../../api/copyProposals'
import i18n, { overriddenKeys } from '../../../i18n'
import CopyProposalsPage from '../CopyProposalsPage'

vi.mock('../../../api/copyProposals', () => ({ listCopyProposals: vi.fn(), settleCopyProposalLine: vi.fn() }))

const line = (key: string, owner: string, proposed: string | null) => ({
  ns: 'common',
  key,
  owner_value: owner,
  proposed_value: proposed,
  status: 'open' as const,
})
const proposal = (): CopyProposal => ({
  id: 7,
  pr_number: 12,
  pr_url: 'https://github.com/o/r/pull/12',
  lines: [line('brand', 'Hearth', 'Home base'), line('gone', 'Mine', null)],
})
const settled = (p: CopyProposal, key: string, status: 'approved' | 'rejected'): CopyProposal => ({
  ...p,
  lines: p.lines.map((l) => (l.key === key ? { ...l, status } : l)),
})

beforeEach(() => {
  let server = proposal()
  vi.mocked(listCopyProposals).mockResolvedValue([server])
  vi.mocked(settleCopyProposalLine).mockImplementation(async (_id, verdict, ref) => {
    server = settled(server, ref.key, verdict === 'approve' ? 'approved' : 'rejected')
    return server
  })
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  overriddenKeys.clear()
})

describe('Copy proposals page', () => {
  it('says plainly when a line deletes the key', async () => {
    render(<CopyProposalsPage />)
    expect(await screen.findByText(/deletes the key/)).toBeTruthy()
    expect(screen.getByText('Home').tagName).toBe('MARK')
    expect(screen.getByText('base').tagName).toBe('MARK')
  })

  it('approve and reject each post their verdict for that line', async () => {
    render(<CopyProposalsPage />)
    const [approve] = await screen.findAllByText('Approve')
    fireEvent.click(approve)
    await waitFor(() => expect(settleCopyProposalLine).toHaveBeenCalledWith(7, 'approve', expect.objectContaining({ key: 'brand' })))
    expect(i18n.getResource('en', 'common', 'brand')).toBe('Home base')
    fireEvent.click(await screen.findByText('Reject'))
    await waitFor(() => expect(settleCopyProposalLine).toHaveBeenCalledWith(7, 'reject', expect.objectContaining({ key: 'gone' })))
    expect(await screen.findByText('Nothing waiting.')).toBeTruthy()
  })

  it('approve all settles every open line, then shows the empty state', async () => {
    render(<CopyProposalsPage />)
    fireEvent.click(await screen.findByText('Approve all'))
    expect(await screen.findByText('Nothing waiting.')).toBeTruthy()
    expect(settleCopyProposalLine).toHaveBeenCalledTimes(2)
  })

  it('a 409 shows her current wording and is not retried', async () => {
    const body = { detail: { code: 'COPY_OVERRIDE_CHANGED', message: 'x', params: { current: 'Hers now' } } }
    vi.mocked(settleCopyProposalLine).mockRejectedValue(new ApiError(new Response(null, { status: 409 }), body))
    render(<CopyProposalsPage />)
    fireEvent.click(await screen.findByText('Approve all'))
    expect(await screen.findByText(/Hers now/)).toBeTruthy()
    expect(settleCopyProposalLine).toHaveBeenCalledTimes(1)
    expect(screen.getAllByText('Approve')).toHaveLength(1)
  })
})
