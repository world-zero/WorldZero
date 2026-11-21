import { useState, useSyncExternalStore, type ReactNode } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { heldInstallPrompt, subscribeInstallPrompt } from '../../utils/installPrompt'
import type { InstallPlatform } from '../../utils/installAsk'
import InstallDialog from './InstallDialog'
import InstallWisp from './InstallWisp'
import './installCopy'
import './installAsk.css'

type Phase = 'ask' | 'share' | 'add' | 'tapAdd' | 'done' | 'steps' | 'installed' | 'later'

interface Props {
  readonly platform: InstallPlatform
  /** The one second ask: "I knocked" copy, and either button ends it. */
  readonly reask?: boolean
  /** The player answered: the host records it so the ask never returns. */
  readonly onAnswered: () => void
  readonly onClose: () => void
}

const B = { b: <b /> }

function Icon({ round, big }: { readonly round: boolean; readonly big?: boolean }) {
  return (
    <div className={`wzi-icon ${round ? 'wzi-icon--round' : ''} ${big ? 'wzi-icon--big' : ''}`}>
      <span className="wzi-icon-word">{'WØ'}</span>
    </div>
  )
}

/** The ask (inline under the praxis or Home) and, past "Show me how", full-screen steps. */
export default function InstallFlow({ platform, reask = false, onAnswered, onClose }: Props) {
  const { t } = useTranslation('install')
  const held = useSyncExternalStore(subscribeInstallPrompt, heldInstallPrompt, () => null)
  const [phase, setPhase] = useState<Phase>('ask')
  const iphone = platform === 'iphone'
  const go = (p: Phase) => () => setPhase(p)

  const moveIn = async () => {
    if (reask) onAnswered()
    if (iphone) return setPhase('share')
    if (!held) return setPhase('steps')
    try {
      await held.prompt()
    } catch {
      return setPhase('steps')
    }
    setPhase('installed')
  }
  const notYet = () => {
    onAnswered()
    setPhase('later')
  }
  const finish = () => {
    onAnswered()
    onClose()
  }

  const overlay = (id: string, children: ReactNode, cls = '') => (
    <InstallDialog labelledBy={id} className={`wzi-overlay ${cls}`}>
      {children}
    </InstallDialog>
  )

  const stepCard = (
    id: string,
    k: 'share' | 'add' | 'tapAdd',
    n: number,
    next: Phase,
    back: Phase,
  ) => (
    <section className="wzi-card wzi-pop" aria-labelledby={id}>
      <div className="wzi-pips" aria-hidden="true">
        {[1, 2, 3].map((i) => (
          <span key={i} className={i <= n ? 'on' : ''} />
        ))}
      </div>
      <span className="wzi-kick">{t(`${k}.kicker`)}</span>
      <h2 className="wzi-h" id={id}>{t(`${k}.title`)}</h2>
      <p className="wzi-p"><Trans t={t} i18nKey={`${k}.body`} components={B} /></p>
      <div className="wzi-row">
        <button type="button" className="wzi-btn wzi-btn-go" onClick={go(next)}>{t(`${k}.next`)}</button>
        <button type="button" className="wzi-btn wzi-btn-ghost" onClick={go(back)}>{t('back')}</button>
      </div>
    </section>
  )

  if (phase === 'share')
    return overlay(
      's1',
      <>
        {stepCard('s1', 'share', 1, 'add', 'ask')}
        <div className="wzi-say wzi-pop wzi-share-say">{t('share.say')}</div>
        <InstallWisp pose="down" confidence={0.6} className="wzi-share-wisp" />
        <div className="wzi-crumbs wzi-share-crumbs" aria-hidden="true"><span /><span /><span /><span /><span /></div>
      </>,
    )

  if (phase === 'add')
    return overlay(
      's2',
      <>
        {stepCard('s2', 'add', 2, 'tapAdd', 'share')}
        <div className="wzi-shelf wzi-shelfrow wzi-pop" aria-hidden="true">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3.5" y="3.5" width="17" height="17" rx="4" />
            <path d="M12 8v8" />
            <path d="M8 12h8" />
          </svg>
          <span>{t('add.row')}</span>
        </div>
        <InstallWisp pose="sign" confidence={0.62} size={64} className="wzi-add-wisp" />
        <div className="wzi-crumbs wzi-add-crumbs" aria-hidden="true"><span /><span /></div>
        <div className="wzi-say wzi-pop wzi-add-say">{t('add.say')}</div>
      </>,
    )

  if (phase === 'tapAdd')
    return overlay(
      's3',
      <>
        {stepCard('s3', 'tapAdd', 3, 'done', 'add')}
        <div className="wzi-center-icon wzi-pop">
          <div className="wzi-icon">
            <InstallWisp pose="home" confidence={0.7} size={43} className="" />
            <span className="wzi-icon-word">{'WØ'}</span>
          </div>
          <span className="wzi-iconlabel">{t('iconLabel')}</span>
        </div>
        <div className="wzi-say wzi-pop wzi-tap-say">{t('tapAdd.say')}</div>
      </>,
    )

  if (phase === 'done' || phase === 'installed') {
    const chrome = phase === 'installed'
    return overlay(
      's4',
      <>
        <section className="wzi-card wzi-pop" aria-labelledby="s4">
          <span className="wzi-kick">{t(chrome ? 'installed.kicker' : 'done.kicker')}</span>
          <h2 className="wzi-h" id="s4">{t(chrome ? 'installed.title' : 'done.title')}</h2>
          <p className="wzi-p">{t(chrome ? 'installed.body' : 'done.body')}</p>
          <div className="wzi-row">
            <button type="button" className="wzi-btn wzi-btn-go" onClick={finish}>{t(chrome ? 'installed.next' : 'done.next')}</button>
          </div>
          {!chrome && (
            <button type="button" className="wzi-link" onClick={go('share')}>{t('done.restart')}</button>
          )}
        </section>
        <div className="wzi-confetti wzi-done-confetti" aria-hidden="true"><span /><span /><span /><span /><span /><span /></div>
        <div className="wzi-center-icon wzi-center-icon--done">
          <Icon round={chrome} />
          <span className="wzi-iconlabel">{t('iconLabel')}</span>
        </div>
        <InstallWisp pose="burst" confidence={0.82} size={70} className="wzi-done-wisp" />
      </>,
    )
  }

  if (phase === 'steps')
    return overlay(
      's5',
      <>
        <div className="wzi-crumbs wzi-crumbs--up wzi-up-crumbs" aria-hidden="true"><span /><span /><span /><span /><span /></div>
        <InstallWisp pose="up" confidence={0.62} size={66} className="wzi-up-wisp" />
        <div className="wzi-say wzi-pop wzi-up-say">{t('manual.say')}</div>
        <section className="wzi-card wzi-pop" aria-labelledby="s5">
          <span className="wzi-kick">{t('manual.kicker')}</span>
          <h2 className="wzi-h" id="s5">{t('manual.title')}</h2>
          <p className="wzi-p"><Trans t={t} i18nKey="manual.body" components={B} /></p>
          <div className="wzi-row">
            <button type="button" className="wzi-btn wzi-btn-go" onClick={go('installed')}>{t('manual.next')}</button>
            <button type="button" className="wzi-btn wzi-btn-ghost" onClick={go('ask')}>{t('back')}</button>
          </div>
        </section>
      </>,
      'wzi-overlay--manual',
    )

  if (phase === 'later') {
    const title = reask ? 'reask.stopTitle' : 'later.title'
    return (
      <div className="wzi-stage">
        <InstallWisp pose="shrink" confidence={reask ? 0.35 : 0.3} size={66} held={reask ? undefined : 'bindle'} className="" />
        <div className="wzi-say wzi-pop">{t(reask ? 'reask.stopSay' : 'later.say')}</div>
        <section className="wzi-sheet wzi-pop" aria-labelledby="later-h">
          <h2 className="wzi-h" id="later-h">{t(title)}</h2>
          <p className="wzi-p"><Trans t={t} i18nKey={reask ? 'reask.stopBody' : 'later.body'} components={B} /></p>
          <button type="button" className="wzi-link" onClick={onClose}>{t(reask ? 'reask.close' : 'later.close')}</button>
        </section>
      </div>
    )
  }

  const chromeTap = !iphone && !!held
  const primaryLabel = reask || chromeTap ? 'ask.moveIn' : 'ask.showMe'
  const foot = iphone ? 'ask.footIphone' : held ? 'ask.footChrome' : 'ask.footManual'
  return (
    <div className={`wzi-stage ${reask ? 'wzi-stage--window' : ''}`} data-testid="install-ask">
      {reask && <div className="wzi-window wzi-pop" aria-hidden="true" />}
      <InstallWisp
        pose={reask ? 'knock' : 'peek'}
        confidence={reask ? 0.6 : 0.55}
        held={reask ? 'letter' : 'bindle'}
        className=""
      />
      <div className="wzi-say wzi-pop">{t(reask ? 'reask.say' : 'ask.say')}</div>
      <section className="wzi-sheet wzi-pop" aria-labelledby="ask-h">
        <div className="wzi-band" />
        <span className="wzi-kick">{t(reask ? 'reask.kicker' : 'ask.kicker')}</span>
        <h2 className="wzi-h" id="ask-h">{t(reask ? 'reask.title' : 'ask.title')}</h2>
        <p className="wzi-p">
          {reask ? (
            <Trans
              t={t}
              i18nKey="reask.body"
              values={{ why: t(iphone ? 'reask.whyIphone' : 'reask.whyAndroid') }}
              components={B}
            />
          ) : (
            <Trans t={t} i18nKey={iphone ? 'ask.bodyIphone' : 'ask.bodyAndroid'} components={B} />
          )}
        </p>
        <div className="wzi-row">
          <button type="button" className="wzi-btn wzi-btn-go" onClick={moveIn}>{t(primaryLabel)}</button>
          <button type="button" className="wzi-btn wzi-btn-ghost" onClick={reask ? () => (onAnswered(), setPhase('later')) : notYet}>
            {t(reask ? 'reask.stop' : 'ask.notYet')}
          </button>
        </div>
        <p className="wzi-foot">{t(reask ? 'reask.foot' : foot)}</p>
      </section>
    </div>
  )
}
