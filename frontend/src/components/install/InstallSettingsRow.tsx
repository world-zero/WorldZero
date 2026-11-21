import { useState, useSyncExternalStore } from 'react'
import { useTranslation } from 'react-i18next'
import { installPlatform } from '../../utils/installAsk'
import { heldInstallPrompt, isStandalone, promptInstall, subscribeInstallPrompt } from '../../utils/installPrompt'
import InstallAndroidSteps from './InstallAndroidSteps'
import './installCopy'
import './installAsk.css'

/** Android's way back to the install steps; the iPhone's lives in the push-blocked card beside it (#4052). */
export default function InstallSettingsRow() {
  const { t } = useTranslation('install')
  const held = useSyncExternalStore(subscribeInstallPrompt, heldInstallPrompt, () => null)
  const [open, setOpen] = useState(false)
  if (installPlatform() !== 'android' || isStandalone()) return null
  return (
    <div className="wzi-settings" data-testid="settings-install">
      <button
        type="button"
        className="btn-outline"
        aria-expanded={held ? undefined : open}
        onClick={() => (held ? void promptInstall().catch(() => setOpen(true)) : setOpen((v) => !v))}
      >
        {t(held ? 'settings.install' : 'settings.action')}
      </button>
      {open && !held && <InstallAndroidSteps />}
    </div>
  )
}
