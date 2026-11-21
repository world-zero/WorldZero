import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import Wisp, { type WispHat, type WispPose, type WispProp } from '../../pages/onboarding/Wisp'
import './installCopy'
import './installAsk.css'

interface Props {
  readonly pose: WispPose
  readonly confidence: number
  /** Positions the poke button; the layout classes live in installAsk.css. */
  readonly className: string
  readonly size?: number
  readonly held?: WispProp
  readonly hat?: WispHat
}

/** The wisp as a button: a poke makes it boing for 700ms (the design's startle). */
export default function InstallWisp({ pose, confidence, className, size = 75, held, hat }: Props) {
  const { t } = useTranslation('install')
  const [boing, setBoing] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])
  const poke = () => {
    clearTimeout(timer.current)
    setBoing(true)
    timer.current = setTimeout(() => setBoing(false), 700)
  }
  return (
    <button type="button" className={`wzi-poke ${className}`} aria-label={t('poke')} onClick={poke}>
      {/* The wisp is one character in both themes: dark-scoped ink and cream, as on the onboarding stage. */}
      <span className="onboarding-arc wzi-wisp" data-theme="dark">
        <Wisp size={size} confidence={confidence} pose={boing ? 'boing' : pose} held={held} hat={hat} />
      </span>
    </button>
  )
}
