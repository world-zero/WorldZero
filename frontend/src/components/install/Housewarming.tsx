import { useState } from 'react'
import { createPortal } from 'react-dom'
import { Trans, useTranslation } from 'react-i18next'
import { turnOnAskedPush } from '../push/askedPush'
import InstallWisp from './InstallWisp'
import './installCopy'
import './installAsk.css'

interface Props {
  readonly vapidKey: string
  readonly name: string
  readonly platform: 'iphone' | 'android'
  /** Any answer: the host records it so the welcome never returns. */
  readonly onAnswered: () => void
  readonly onClose: () => void
}

const POSE = { hello: 'burst', yes: 'knock', no: 'home' } as const
const B = { b: <b /> }

/** First open from the home screen: the wisp bursts out of the icon and the push ask happens here (#4052). */
export default function Housewarming({ vapidKey, name, platform, onAnswered, onClose }: Props) {
  const { t } = useTranslation('install')
  const [step, setStep] = useState<keyof typeof POSE>('hello')
  const [busy, setBusy] = useState(false)

  const answer = async (yes: boolean) => {
    setBusy(true)
    let ok = false
    try {
      ok = yes && (await turnOnAskedPush(vapidKey)) === 'ok'
    } catch {
      // The browser or service worker said no; the "no" panel points at Settings.
    }
    onAnswered()
    setStep(ok ? 'yes' : 'no')
    setBusy(false)
  }

  return createPortal(
    <div className="wzi-welcome" role="dialog" aria-labelledby="hw-h" data-testid="housewarming">
      <div className="wzi-confetti wzi-confetti--wide" aria-hidden="true"><span /><span /><span /><span /><span /><span /><span /></div>
      <div className={`wzi-icon wzi-icon--big ${platform === 'android' ? 'wzi-icon--round' : ''}`}>
        <span className="wzi-icon-word">{'WØ'}</span>
      </div>
      <InstallWisp pose={POSE[step]} confidence={0.95} size={94} hat="teacup" className="" />
      <section className="wzi-sheet wzi-pop" key={step}>
        <div className="wzi-band" />
        {step === 'hello' ? (
          <>
            <span className="wzi-kick">{t('welcome.kicker')}</span>
            <h1 className="wzi-h" id="hw-h">{t('welcome.title')}</h1>
            <p className="wzi-p">
              {name ? (
                <Trans t={t} i18nKey="welcome.body" values={{ name }} components={B} />
              ) : (
                <Trans t={t} i18nKey="welcome.bodyNoName" components={B} />
              )}
            </p>
            <div className="wzi-row">
              <button type="button" className="wzi-btn wzi-btn-go" disabled={busy} onClick={() => answer(true)}>{t('welcome.yes')}</button>
              <button type="button" className="wzi-btn wzi-btn-ghost" disabled={busy} onClick={() => answer(false)}>{t('welcome.no')}</button>
            </div>
            <p className="wzi-foot">{t('welcome.foot')}</p>
          </>
        ) : (
          <>
            <h1 className="wzi-h" id="hw-h">{t(step === 'yes' ? 'welcome.yesTitle' : 'welcome.noTitle')}</h1>
            <p className="wzi-p">
              {step === 'yes' ? t('welcome.yesBody') : <Trans t={t} i18nKey="welcome.noBody" components={B} />}
            </p>
            <div className="wzi-row">
              <button type="button" className="wzi-btn wzi-btn-go" onClick={onClose}>{t('welcome.toDesk')}</button>
            </div>
          </>
        )}
      </section>
    </div>,
    document.body,
  )
}
