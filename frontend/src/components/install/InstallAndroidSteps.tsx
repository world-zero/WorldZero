import { Trans, useTranslation } from 'react-i18next'
import './installCopy'
import './installNudge.css'

/** Chrome's menu path, for when it offers no install prompt. Settings shows it beside the iPhone steps. */
export default function InstallAndroidSteps() {
  const { t } = useTranslation('install')
  return (
    <ol className="install-steps">
      {[1, 2].map((n) => (
        <li key={n} className="install-step">
          <span aria-hidden className="install-step-num">{n}</span>
          <span className="install-step-text">
            <Trans t={t} i18nKey={`steps.android.${n}` as 'steps.android.1'} components={{ b: <strong /> }} />
          </span>
        </li>
      ))}
    </ol>
  )
}
