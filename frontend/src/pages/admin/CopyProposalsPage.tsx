import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listCopyProposals, settleCopyProposalLine, type CopyProposal, type CopyProposalLine } from '../../api/copyProposals'
import { showApproved } from '../../components/admin/CopyEditor'
import i18n from '../../i18n'
import { ErrorCode, extractError, extractErrorCode, extractErrorParams } from '../../utils/errors'
import { typoDiff } from '../../utils/typoFix'
import './adminList.css'

const lineId = (proposalId: number, line: CopyProposalLine) => `${proposalId}:${line.ns}:${line.key}`

function Proposed({ line }: { line: CopyProposalLine }) {
  const { t } = useTranslation('admin')
  if (line.proposed_value === null) return <em>{t('copyProposals.deleted')}</em>
  const diff = typoDiff(line.owner_value, line.proposed_value)
  if (!diff) return <>{line.proposed_value}</>
  return (
    <>
      {diff.words.map((word, i) => (
        <span key={i}>
          {i > 0 && ' '}
          {diff.changed[i] ? <mark>{word}</mark> : word}
        </span>
      ))}
    </>
  )
}

export default function CopyProposalsPage() {
  const { t } = useTranslation('admin')
  const [proposals, setProposals] = useState<CopyProposal[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Lines whose approval hit a 409, by id; their approve control is hidden.
  const [changed, setChanged] = useState<Record<string, string>>({})

  useEffect(() => {
    listCopyProposals()
      .then(setProposals)
      .catch((err) => setError(extractError(err, t('copyProposals.loadError'))))
  }, [])

  /** False when the line did not settle; a 409 is shown on the line and never retried. */
  const settle = async (proposal: CopyProposal, line: CopyProposalLine, verdict: 'approve' | 'reject') => {
    try {
      const next = await settleCopyProposalLine(proposal.id, verdict, line)
      if (verdict === 'approve') showApproved(line, line.proposed_value)
      setProposals((all) => (all ?? []).map((p) => (p.id === next.id ? next : p)).filter((p) => p.lines.some((l) => l.status === 'open')))
      return true
    } catch (err) {
      if (extractErrorCode(err) === ErrorCode.copyOverrideChanged) {
        const live = extractErrorParams(err).current
        const current = typeof live === 'string' ? live : ''
        i18n.addResource('en', line.ns, line.key, current)
        setChanged((c) => ({ ...c, [lineId(proposal.id, line)]: current }))
      } else {
        setError(extractError(err, t('copyProposals.settleError')))
      }
      return false
    }
  }

  const approveAll = async () => {
    setError(null)
    for (const proposal of proposals ?? []) {
      for (const line of proposal.lines.filter((l) => l.status === 'open')) {
        if (!(await settle(proposal, line, 'approve'))) return
      }
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <header className="adm-head">
        <div>
          <h1 className="adm-h1">{t('console.rail.items.copyProposals')}</h1>
          <p className="adm-lede">{t('copyProposals.lede')}</p>
        </div>
        {proposals && proposals.length > 0 && (
          <div className="adm-btns">
            <button type="button" className="adm-btn adm-btn-pri" onClick={() => void approveAll()}>
              {t('copyProposals.approveAll')}
            </button>
          </div>
        )}
      </header>
      {error && <p className="adm-err">{error}</p>}
      {proposals?.length === 0 && <p className="adm-empty">{t('copyProposals.empty')}</p>}
      {proposals && proposals.length > 0 && <p className="adm-muted">{t('copyProposals.rerun')}</p>}
      {proposals?.map((proposal) => (
        <section key={proposal.id} className="adm-card flex flex-col gap-3 p-4">
          <a href={proposal.pr_url} target="_blank" rel="noreferrer" className="adm-open">
            {t('copyProposals.pr', { number: proposal.pr_number })}
          </a>
          {proposal.lines
            .filter((l) => l.status === 'open')
            .map((line) => {
              const clash = changed[lineId(proposal.id, line)]
              return (
                <div key={lineId(proposal.id, line)} className="flex flex-col gap-1">
                  <code>{`${line.ns}:${line.key}`}</code>
                  <p className="adm-muted">
                    {t('copyProposals.yours')}: {line.owner_value}
                  </p>
                  <p className="adm-muted">
                    {t('copyProposals.proposed')}: <Proposed line={line} />
                  </p>
                  {clash !== undefined && <p className="adm-err">{t('copyProposals.changed', { current: clash })}</p>}
                  <div className="adm-btns">
                    {clash === undefined && (
                      <button type="button" className="adm-btn" onClick={() => void settle(proposal, line, 'approve')}>
                        {t('copyProposals.approve')}
                      </button>
                    )}
                    <button type="button" className="adm-btn adm-btn-dng" onClick={() => void settle(proposal, line, 'reject')}>
                      {t('copyProposals.reject')}
                    </button>
                  </div>
                </div>
              )
            })}
        </section>
      ))}
    </div>
  )
}
