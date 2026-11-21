import { useEffect, useState, type CSSProperties } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../auth/AuthContext'
import { getMyCharacters, setActiveCharacter } from '../api/me'
import type { CharacterOut } from '../api/auth'
import { factionName } from '../utils/factions'
import FactionAvatar from './avatar/FactionAvatar'
import BottomSheet from './ui/BottomSheet'
import './characterSwitcherSheet.css'

/**
 * MOBILE active-character switcher (#516): a bottom sheet listing the account's
 * lives; tap adopts the `POST /me/active-character` answer (#1383). Mobile field
 * desks only (#2354).
 *
 * "Create new character" shows only on the server's
 * `can_create_additional_character` — hidden, not padlocked (#2111, #1560).
 * Callers hide the trigger via `rosterOffersAChoice` when there's nothing to offer.
 *
 * Drawn by `BottomSheet`, at the document root (#1591).
 */

export default function CharacterSwitcherSheet({
  open,
  activeCharacterId,
  onClose,
}: {
  open: boolean
  activeCharacterId: number
  onClose: () => void
}) {
  const { t } = useTranslation('common')
  const { user, applyUser } = useAuth()
  const navigate = useNavigate()
  const [lives, setLives] = useState<CharacterOut[]>([])
  const [switching, setSwitching] = useState<number | null>(null)

  useEffect(() => {
    if (!open) return
    void getMyCharacters().then(setLives).catch(() => setLives([]))
  }, [open])

  if (!open) return null

  const enterLife = async (id: number) => {
    if (id === activeCharacterId) {
      onClose()
      return
    }
    setSwitching(id)
    try {
      // The POST answers the new `CurrentUser`; adopt it (#1383).
      applyUser(await setActiveCharacter(id))
      onClose()
    } finally {
      setSwitching(null)
    }
  }

  return (
    <BottomSheet
      label={t('fieldDesk.home.switcher.title')}
      scrimLabel={t('fieldDesk.home.switcher.close')}
      onClose={onClose}
      panelClass="switcher-sheet"
    >
      <div style={sheetTitle}>{t('fieldDesk.home.switcher.title')}</div>

        <CharacterSwitcherRows
          lives={lives}
          activeCharacterId={activeCharacterId}
          onSelect={enterLife}
          switching={switching}
        />

        {user?.can_create_additional_character && (
          <button type="button" onClick={() => navigate('/characters/create')} style={{ ...sheetAction, borderTop: '1px solid var(--color-border)' }}>
            <span style={actionIcon}>+</span>
            {t('fieldDesk.home.switcher.createNew')}
          </button>
        )}
    </BottomSheet>
  )
}

/** Roster rows, extracted to be testable with renderToStaticMarkup. */
export function CharacterSwitcherRows({
  lives,
  activeCharacterId,
  onSelect,
  switching = null,
}: {
  lives: CharacterOut[]
  activeCharacterId: number
  onSelect: (id: number) => void
  switching?: number | null
}) {
  const { t } = useTranslation('common')
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {lives.map((life) => {
        const isActive = life.id === activeCharacterId
        return (
          <button
            key={life.id}
            type="button"
            onClick={() => onSelect(life.id)}
            disabled={switching != null}
            data-testid={`switcher-row-${life.id}`}
            data-active={isActive ? 'true' : 'false'}
            style={switchRow}
          >
            <span style={{ ...miniRing, background: 'var(--faction-default-rainbow-conic)' }}>
              <FactionAvatar character={life} size={40} badge={false} />
            </span>
            <span style={{ flex: 1, minWidth: 0, textAlign: 'left' }}>
              <span style={rowName}>{life.display_name}</span>
              <span style={rowMeta}>
                {t('fieldDesk.home.switcher.meta', {
                  faction: factionName(life.faction_slug),
                  level: life.level,
                  points: life.score,
                })}
              </span>
            </span>
            {isActive ? (
              <span aria-hidden style={{
                color: 'var(--faction-default-card-muted)', flex: 'none',
                // eslint-disable-next-line local/no-raw-style-values -- ornament: check dingbat marking the active life
                fontSize: 16,
              }}>✓</span>
            ) : (
              <span style={rowTapHint}>{t('fieldDesk.home.switcher.tapToUse')}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

const sheetTitle: CSSProperties = {
  fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 'var(--text-content)',
  color: 'var(--color-text-primary)', margin: '0 var(--space-xs) var(--space-sm)',
}
const switchRow: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 'var(--space-md)', padding: 'var(--space-md) var(--space-xs)',
  borderBottom: '1px solid var(--color-border)', cursor: 'pointer',
  background: 'none', border: 'none', borderBottomStyle: 'solid',
  borderBottomWidth: 1, borderBottomColor: 'var(--color-border)', width: '100%',
}
const miniRing: CSSProperties = {
  width: 44, height: 44, borderRadius: '50%', flex: 'none',
  // eslint-disable-next-line local/no-raw-style-values -- ornament: this inset *is* the drawn ring stroke around the mini avatar, not spacing
  padding: 2,
}
const rowName: CSSProperties = {
  display: 'block', fontFamily: 'var(--font-display)', fontStyle: 'italic',
  fontSize: 'var(--text-content)', color: 'var(--color-text-primary)',
  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
}
const rowMeta: CSSProperties = {
  display: 'block', fontSize: 'var(--text-md)', letterSpacing: '0.14em', textTransform: 'uppercase',
  color: 'var(--color-text-secondary)', marginTop: 'var(--space-xs)',
}
const rowTapHint: CSSProperties = {
  fontSize: 'var(--text-md)', letterSpacing: '0.1em', textTransform: 'uppercase',
  color: 'var(--color-text-tertiary)', flex: 'none',
}
const sheetAction: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 'var(--space-md)', padding: 'var(--space-lg) var(--space-xs)', width: '100%',
  color: 'var(--color-text-primary)', fontFamily: 'var(--font-display)',
  fontStyle: 'italic', fontSize: 'var(--text-content)', cursor: 'pointer', background: 'none', border: 'none',
}
const actionIcon: CSSProperties = {
  width: 34, height: 34, borderRadius: '50%', border: '1.5px dashed var(--color-border-strong)',
  // eslint-disable-next-line local/no-raw-style-values -- ornament: '+' glyph centred in the 34px dashed action disc
  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16,
  color: 'var(--color-text-secondary)', flex: 'none',
}
