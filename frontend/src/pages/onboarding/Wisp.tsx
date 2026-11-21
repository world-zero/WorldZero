import { useId, type CSSProperties, type ReactNode } from 'react'
import './motion/shared.css'
import './motion/generated.css'
import './motion/wisp.css'

export type WispHat = 'crown' | 'wizard' | 'teacup'
/** Install-flow poses (#4052); the CSS in `components/install/wispPoses.css` animates each. */
export type WispPose = 'peek' | 'down' | 'up' | 'sign' | 'home' | 'burst' | 'knock' | 'shrink' | 'boing'
export type WispProp = 'bindle' | 'letter'

export const K = 'var(--faction-default-on-fill)'
export const T = 'var(--faction-default-card-text)'
export const S = (i: number) => `var(--faction-default-stop-${i})`

const WISP =
  'M50 104 C 30 104, 18 90, 18 72 C 18 56, 26 46, 32 36 C 34 42, 38 46, 42 46 C 38 32, 42 16, 52 4 C 54 16, 60 24, 66 30 C 68 24, 72 20, 76 18 C 74 30, 82 46, 82 70 C 82 90, 70 104, 50 104 Z'
// Under a hat the hair is tucked away: same wisp, round on top.
export const BALD =
  'M50 104 C 30 104, 18 90, 18 72 C 18 52, 32 38, 50 38 C 68 38, 82 52, 82 70 C 82 90, 70 104, 50 104 Z'

const ink = { stroke: K, strokeLinejoin: 'round' as const }

export const HATS: Record<WispHat, ReactNode> = {
  crown: (
    <>
      <path d="M21 50 L 23 18 L 36 30 L 50 -6 L 64 30 L 77 18 L 79 50 Z" fill={S(3)} strokeWidth="2" {...ink} />
      <rect x="21" y="40" width="58" height="10" fill={S(3)} stroke={K} strokeWidth="2" />
      <circle cx="50" cy="-6" r="3.6" fill={S(1)} stroke={K} strokeWidth="1.2" />
      <circle cx="50" cy="45" r="3" fill={S(6)} />
    </>
  ),
  wizard: (
    <>
      <path d="M18 52 L 54 -30 L 82 52 Z" fill={S(6)} strokeWidth="2" {...ink} />
      <ellipse cx="50" cy="52" rx="38" ry="8" fill={S(6)} stroke={K} strokeWidth="2" />
      <path d="M54 4 l3 7 l7 3 l-7 3 l-3 7 l-3 -7 l-7 -3 l7 -3 Z" fill={S(3)} />
    </>
  ),
  teacup: (
    <>
      <ellipse cx="50" cy="47" rx="35" ry="7.5" fill={T} stroke={K} strokeWidth="2" />
      <path d="M73 16 C 92 13, 92 37, 69 35" fill="none" stroke={K} strokeWidth="8.5" strokeLinecap="round" />
      <path d="M73 16 C 92 13, 92 37, 69 35" fill="none" stroke={T} strokeWidth="4.5" strokeLinecap="round" />
      <path d="M26 8 C 26 34, 36 46, 50 46 C 64 46, 74 34, 74 8 Z" fill={T} strokeWidth="2" {...ink} />
      <path d="M27.5 21 C 40 27, 60 27, 72.5 21" fill="none" stroke={S(1)} strokeWidth="3.4" />
      <ellipse cx="50" cy="8" rx="24" ry="5.5" fill={S(2)} stroke={K} strokeWidth="2" />
      <path d="M43 -2 q-5 -6 0 -12 q5 -6 0 -12 M57 -4 q5 -6 0 -12" fill="none" stroke={T} strokeWidth="2.2" strokeLinecap="round" opacity=".6" />
    </>
  ),
}

const PROPS: Record<WispProp, ReactNode> = {
  bindle: (
    <>
      <path d="M70 104 L 97 40" stroke={K} strokeWidth="6" strokeLinecap="round" />
      <path d="M70 104 L 97 40" stroke="var(--faction-default-stop-3)" strokeWidth="3" strokeLinecap="round" />
      <path d="M85 38 C 82 24, 112 22, 110 38 C 109 50, 86 52, 85 38 Z" fill={S(7)} stroke={K} strokeWidth="2.2" strokeLinejoin="round" />
      <circle cx="92" cy="36" r="2" fill={T} />
      <circle cx="101" cy="31" r="2" fill={T} />
      <circle cx="103" cy="42" r="2" fill={T} />
      <path d="M94 26 l3 -6 l4 6" fill="none" stroke={K} strokeWidth="2" strokeLinejoin="round" />
    </>
  ),
  letter: (
    <g transform="rotate(-14 84 90)">
      <rect x="72" y="81" width="26" height="18" rx="2" fill={T} stroke={K} strokeWidth="2" />
      <path d="M72 82 L 85 92 L 98 82" fill="none" stroke={K} strokeWidth="2" strokeLinejoin="round" />
      <circle cx="85" cy="91" r="3" fill={S(1)} />
    </g>
  ),
}

interface WispProps {
  /** Width in px; the height follows the drawing. */
  size?: number
  /** 0 (shy) to 1 (bold): how much of the spectrum the body shows. */
  confidence?: number
  hat?: WispHat
  sleeping?: boolean
  pose?: WispPose
  /** Held in the wisp's arm. */
  held?: WispProp
  className?: string
  style?: CSSProperties
}

export default function Wisp({ size = 52, confidence = 0.5, hat, sleeping = false, pose, held, className, style }: WispProps) {
  // Gradient ids are document-global and --conf resolves where the gradient sits: one pair per wisp.
  const id = useId().replace(/:/g, '')
  const path = hat ? BALD : WISP
  return (
    <svg
      className={['pw msc', sleeping && 'wsleep', pose && `pose-${pose}`, className].filter(Boolean).join(' ')}
      viewBox="14 0 72 106"
      width={size}
      height={Math.round((size * 106) / 72)}
      aria-hidden="true"
      data-hat={hat}
      data-sleeping={sleeping || undefined}
      style={{ display: 'block', overflow: 'visible', ['--conf' as string]: confidence, ...style }}
    >
      <defs>
        <linearGradient id={`${id}rain`} gradientUnits="userSpaceOnUse" x1="18" y1="4" x2="82" y2="104">
          {Array.from({ length: 7 }, (_, i) => (
            <stop
              key={i}
              offset={(i / 6).toFixed(3)}
              style={{ stopColor: `color-mix(in srgb, ${S(i + 1)} calc(10% + var(--conf) * 48%), ${T})` }}
            />
          ))}
        </linearGradient>
        <radialGradient id={`${id}shade`} gradientUnits="userSpaceOnUse" gradientTransform="translate(18 4) scale(64 100)" cx=".42" cy=".62" r=".64">
          <stop className="wshade-mid" offset="55%" />
          <stop offset="100%" style={{ stopColor: S(6), stopOpacity: 0.3 }} />
        </radialGradient>
      </defs>
      <g className="w-body">
      <g className="w-pose">
      <g className="msway">
        <path d={path} fill={`url(#${id}rain)`} />
        <path d={path} fill={`url(#${id}shade)`} stroke={K} strokeWidth="2.6" strokeLinejoin="round" />
        <ellipse className="blush" cx="27" cy="84" rx="8" ry="4.2" />
        <ellipse className="blush" cx="73" cy="84" rx="8" ry="4.2" />
        <g className="eyes">
          <circle cx="38" cy="70" r="10.5" fill={T} stroke={K} strokeWidth="2.2" />
          <circle cx="62" cy="70" r="10.5" fill={T} stroke={K} strokeWidth="2.2" />
          <g className="look">
            <g className="mpup">
              <circle className="pp" cx="38" cy="71" r="5" fill={K} />
              <circle className="pp" cx="62" cy="71" r="5" fill={K} />
              <circle cx="36.4" cy="69.2" r="1.6" fill={T} />
              <circle cx="60.4" cy="69.2" r="1.6" fill={T} />
            </g>
          </g>
        </g>
        <path className="lids" d="M28.5 70 q9.5 8 19 0 M52.5 70 q9.5 8 19 0" fill="none" stroke={K} strokeWidth="2.6" strokeLinecap="round" />
        <path className="smile" d="M46 88 q4 3.4 8 0" fill="none" stroke={K} strokeWidth="2" strokeLinecap="round" />
        <ellipse className="mo" cx="50" cy="89.6" rx="3.6" ry="4.6" fill={K} />
        {held && <g>{PROPS[held]}</g>}
        {hat && (
          <g key={hat} className="hatpop">
            {HATS[hat]}
          </g>
        )}
      </g>
      </g>
      </g>
    </svg>
  )
}
