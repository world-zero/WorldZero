import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { unsubscribeAllEmail, unsubscribeEmail } from '../api/email'
import PageTitle from '../components/ui/PageTitle'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { NOTIFICATION_ROWS } from './settings/notificationPrefs'

type Stage = 'working' | 'one' | 'all' | 'invalid'

/**
 * `/unsubscribe?token=` — where the footer link in a notification mail lands (#2164).
 * Public: mail is read signed out, so the signed token is the credential. Opening the
 * page turns that one event off; "turn them all off" is a second, deliberate click.
 */
export default function Unsubscribe() {
  const { t } = useTranslation('common')
  const token = useSearchParams()[0].get('token') ?? ''
  const [stage, setStage] = useState<Stage>('working')
  const [event, setEvent] = useState('')
  useDocumentTitle(t('unsubscribe.title'))

  useEffect(() => {
    let live = true
    unsubscribeEmail(token)
      .then((key) => {
        if (!live) return
        setEvent(key)
        setStage('one')
      })
      .catch(() => {
        if (live) setStage('invalid')
      })
    return () => {
      live = false
    }
  }, [token])

  const row = NOTIFICATION_ROWS.find((candidate) => candidate.key === event)

  return (
    <div className="py-8 max-w-2xl" data-testid="unsubscribe">
      <PageTitle title={t('unsubscribe.title')} />
      <div className="card p-6 space-y-5 font-body text-base leading-relaxed">
        {stage === 'working' && <p role="status">{t('unsubscribe.working')}</p>}
        {stage === 'invalid' && <p role="alert">{t('unsubscribe.invalid')}</p>}
        {stage === 'one' && (
          <>
            <p role="status">{t('unsubscribe.one', { event: row ? t(row.titleKey) : '' })}</p>
            <button
              type="button"
              className="btn-outline"
              onClick={() =>
                unsubscribeAllEmail(token)
                  .then(() => setStage('all'))
                  .catch(() => setStage('invalid'))
              }
            >
              {t('unsubscribe.all')}
            </button>
          </>
        )}
        {stage === 'all' && <p role="status">{t('unsubscribe.allDone')}</p>}
        <p>
          <Link to="/settings">{t('unsubscribe.settings')}</Link>
        </p>
      </div>
    </div>
  )
}
