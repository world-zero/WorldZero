import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import FactionSigil, { factionSigilRing } from './sigil/FactionSigil'
import { ALBESCENT_FACTION_SLUG, factionName, isKnownFaction } from '../utils/factions'
import type { CharacterOut } from '../api/auth'
import FactionAvatar from './avatar/FactionAvatar'

/**
 * Faction credential card (#271): one structure, re-skinned via
 * `--faction-<slug>-card-*` mapped onto local `--fc-*` vars.
 */

export interface CredentialCardProps {
  displayName: string
  handle: string
  factionSlug?: string | null
  level: number
  score: number
  avatarUrl?: string | null
  /** A real character draws its face through FactionAvatar (monogram when portrait-less); `avatarUrl` is for the creation preview. */
  character?: CharacterOut
  /** Card width in px (default 266 per mock). */
  size?: number
  /** Slight tilt for the FieldDesk roster (degrees). */
  rotation?: number
  /**
   * Stand the portrait ring STILL where the surround already moves (#3024: the
   * profile header's `.alb-profile-edge` band). Drops the `spectrum-dial` class
   * and paints the resting conic inline, since the class carried both.
   */
  stillRing?: boolean
  /** Upload affordance for the creation preview. */
  onAvatarClick?: () => void
}

interface Skin {
  bg: string
  text: string
  accent: string
  muted: string
  font: string
  border: string
}

function skinFor(slug: string | null | undefined): Skin | null {
  // null = neutral: na, factionless, unknown, and albescent (unthemed, #783).
  if (!isKnownFaction(slug)) return null
  const v = (prop: string) => `var(--faction-${slug}-card-${prop})`
  return {
    bg: v('bg'),
    text: v('text'),
    accent: v('accent'),
    muted: v('muted'),
    font: v('font'),
    border: `2px solid ${v('accent')}`,
  }
}

const NEUTRAL: Skin = {
  bg: 'var(--color-bg-surface-alt)',
  text: 'var(--color-text-primary)',
  accent: 'var(--color-text-primary)',
  muted: 'var(--color-text-secondary)',
  font: 'var(--font-display)',
  border: '1px solid var(--color-border-strong)',
}

/** The hoop owns the spectrum (one rainbow per frame): Albescent's own avatar ring would spin inside it, so its face draws as na's disc. */
const stillFace = (slug: string | null | undefined) => (slug === ALBESCENT_FACTION_SLUG ? '' : slug ?? '')

/** FactionAvatar's monogram reads `username[0]`, so the card's own name stands in for it. */
function monogramOf(name: string, factionSlug: string | null | undefined): CharacterOut {
  return {
    all_time_score: 0, avatar_url: '', badges: [], bio: '', created_at: '', display_name: name,
    faction_slug: stillFace(factionSlug), id: 0, invitations: [], level: 0, location: '', score: 0,
    status: 'active', tagline: '', username: name,
  }
}

export default function CredentialCard({
  displayName,
  handle,
  factionSlug,
  level,
  score,
  avatarUrl,
  character,
  size = 266,
  rotation = 0,
  stillRing = false,
  onAvatarClick,
}: CredentialCardProps) {
  const { t } = useTranslation('common')
  const skinned = skinFor(factionSlug)
  const skin = skinned ?? NEUTRAL
  const name = displayName.trim() || t('credential.fallbackName')

  const cardStyle: CSSProperties = {
    ['--fc-bg' as string]: skin.bg,
    ['--fc-text' as string]: skin.text,
    ['--fc-accent' as string]: skin.accent,
    ['--fc-muted' as string]: skin.muted,
    ['--fc-font' as string]: skin.font,
    position: 'relative',
    width: size,
    boxSizing: 'border-box',
    background: 'var(--fc-bg)',
    color: 'var(--fc-text)',
    border: skin.border,
    boxShadow: '0 16px 34px var(--color-cast-shadow)',
    // §4a asymmetric-inset exception: rounds DOWN to one rung.
    padding: 'var(--space-lg)',
    textAlign: 'center',
    overflow: 'hidden',
    transform: rotation ? `rotate(${rotation}deg)` : undefined,
    transition: 'background 220ms ease, border-color 220ms ease, color 220ms ease',
  }

  return (
    <div style={cardStyle}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: 'var(--text-md)',
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: 'var(--fc-muted)',
        }}
      >
        <span>@{handle}</span>
      </div>

      {/* A <button> only as an upload affordance: on FieldDesk the card is already a button. */}
      <div style={{ display: 'flex', justifyContent: 'center', margin: 'var(--space-lg) 0 var(--space-md)' }}>
        {(() => {
          const ringStyle: CSSProperties = {
            position: 'relative',
            width: 136,
            height: 136,
            borderRadius: '50%',
            padding: 'var(--space-xs)',
            boxSizing: 'border-box',
            // Themed: accent hoop. Unaffiliated: `.spectrum-dial` below (ADR-0039),
            // or the conic inline when `stillRing` drops the class.
            background: skinned
              ? 'var(--fc-accent)'
              : stillRing
                ? 'var(--faction-default-rainbow-conic)'
                : undefined,
            border: 'none',
            cursor: onAvatarClick ? 'pointer' : 'default',
            boxShadow: '0 4px 14px var(--color-cast-shadow)',
          }
          /* The na ring is CLASSED, not inlined (#2992). Albescent is unthemed
           * (#783), so it gets the rainbow, and an `.alb-moves` ancestor sets it
           * turning (reduced-motion gated). `stillRing` opts out (#3024); census
           * in `albescentSpectraMove.test.tsx`. */
          const ringClass = skinned || stillRing ? undefined : 'spectrum-dial'
          const inner = (
            <div
              style={{
                width: '100%',
                height: '100%',
                borderRadius: '50%',
                overflow: 'hidden',
                background: 'var(--fc-bg)',
              }}
            >
              {character ? (
                <FactionAvatar character={{ ...character, faction_slug: stillRing ? stillFace(character.faction_slug) : character.faction_slug }} size={128} badge={false} />
              ) : avatarUrl ? (
                <img
                  src={avatarUrl}
                  alt={name}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              ) : (
                <FactionAvatar character={monogramOf(name, factionSlug)} size={128} badge={false} />
              )}
            </div>
          )
          // One string for tooltip and accessible name; it only opens a file input — no drop (#1263).
          const uploadLabel = t('credential.uploadTitle')
          return onAvatarClick ? (
            <button
              type="button"
              onClick={onAvatarClick}
              aria-label={uploadLabel}
              title={uploadLabel}
              className={ringClass}
              style={ringStyle}
            >
              {inner}
            </button>
          ) : (
            <div className={ringClass} style={ringStyle}>{inner}</div>
          )
        })()}
      </div>

      <div
        style={{
          fontFamily: 'var(--fc-font)',
          fontStyle: skinned ? undefined : 'italic',
          fontSize: 'var(--text-title)',
          lineHeight: 1.05,
          color: 'var(--fc-text)',
          overflowWrap: 'anywhere',
        }}
      >
        {name}
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          gap: 'var(--space-md)',
          borderTop: '1px solid var(--fc-muted)',
          marginTop: 'var(--space-lg)',
          paddingTop: 'var(--space-md)',
        }}
      >
        {/* The faction is the sigil, named only for screen readers (#1626). Slug-blind:
            `factionSigilRing` overrides the hoop only for a mark that rings itself (#1658). */}
        <span
          role="img"
          aria-label={factionName(factionSlug)}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            flex: 'none',
            width: 42,
            height: 42,
            borderRadius: '50%',
            border: `2px solid ${factionSigilRing(factionSlug) ?? 'var(--fc-accent)'}`,
            background: 'transparent',
          }}
        >
          <FactionSigil slug={factionSlug} size={28} />
        </span>
        <span
          style={{
            fontSize: 'var(--text-lg)',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            color: 'var(--fc-muted)',
          }}
        >
          {t('credential.lvl', { level })}
        </span>
        <span style={{ fontFamily: 'var(--fc-font)', fontSize: 'var(--text-content)', color: 'var(--fc-accent)' }}>
          {score}
          <span
            style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-md)',
              marginLeft: 'var(--space-xs)',
              color: 'var(--fc-muted)',
              letterSpacing: '0.06em',
            }}
          >
            {t('credential.pts')}
          </span>
        </span>
      </div>
    </div>
  )
}
