/** Agent PRs proposing changes to copy the owner edited live; every route needs `edit_copy`. */
import { apiGet, apiPost } from './client'
import type { components } from './generated/schema'

export type CopyProposal = components['schemas']['CopyProposalOut']
export type CopyProposalLine = components['schemas']['CopyProposalLineOut']

export async function listCopyProposals(): Promise<CopyProposal[]> {
  const { data } = await apiGet('/copy-proposals')
  return data
}

export async function settleCopyProposalLine(
  id: number,
  verdict: 'approve' | 'reject',
  line: { ns: string; key: string },
): Promise<CopyProposal> {
  const { data } = await apiPost(`/copy-proposals/{proposal_id}/${verdict}`, {
    params: { path: { proposal_id: id } },
    body: { ns: line.ns, key: line.key },
  })
  return data
}
