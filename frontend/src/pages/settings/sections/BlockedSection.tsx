import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../../auth/AuthContext'
import { listBlocks, unblockCharacter, type BlockListItem } from '../../../api/relationships'
import { CARD_CTA } from '../../../components/ctaTapFloor'
import FactionAvatar from '../../../components/avatar/FactionAvatar'
import { authorToCharacter } from '../../../components/comments/shared'
import { formatDate } from '../../../utils/dates'
import type { SettingsSectionProps } from '../../Settings'
import SettingsCard from '../SettingsCard'

const QUIET = 'font-body mt-[var(--space-lg)] mb-0 text-[length:var(--text-content)] text-[var(--color-text-tertiary)]'

/** The active character's block list; a block belongs to a character (ADR-0077). */
export default function BlockedSection({ sectionId }: SettingsSectionProps) {
  const { t } = useTranslation('common')
  const { user } = useAuth()
  const characterId = user?.character?.id
  const [blocks, setBlocks] = useState<BlockListItem[] | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [failedId, setFailedId] = useState<number | null>(null)

  useEffect(() => {
    setLoadFailed(false)
    if (characterId === undefined) return setBlocks([])
    setBlocks(null)
    let live = true
    listBlocks().then(
      (rows) => live && setBlocks(rows),
      () => live && setLoadFailed(true),
    )
    return () => {
      live = false
    }
  }, [characterId])

  const unblock = async (id: number) => {
    setFailedId(null)
    try {
      await unblockCharacter(id)
      setBlocks((rows) => rows && rows.filter((r) => r.character_id !== id))
    } catch {
      setFailedId(id)
    }
  }

  return (
    <SettingsCard sectionId={sectionId} title={t('settings.blocked.eyebrow')} lead={t('settings.blocked.lead')}>
      {blocks === null ? (
        loadFailed && (
          <p role="alert" className={QUIET}>
            {t('settings.blocked.loadFailed')}
          </p>
        )
      ) : blocks.length === 0 ? (
        <p className={QUIET}>{t('settings.blocked.empty')}</p>
      ) : (
        <ul className="list-none m-0 p-0" data-testid="settings-blocked-list">
          {blocks.map((b, i) => (
            <li
              key={b.character_id}
              className={`font-body flex items-center gap-[var(--space-md)] pt-[var(--space-lg)] ${i === blocks.length - 1 ? '' : 'pb-[var(--space-lg)] border-b border-[var(--color-border)]'}`}
            >
              <FactionAvatar
                character={authorToCharacter({ id: b.character_id, username: b.display_name, display_name: b.display_name, avatar_url: b.avatar_url, faction_slug: b.faction_slug, name_state: 'ok' })}
                size={40}
              />
              <div className="min-w-0 flex-1 text-[length:var(--text-content)]">
                <Link to={`/characters/${b.character_id}`} className="text-[var(--color-text-primary)] [overflow-wrap:anywhere]">
                  {b.display_name}
                </Link>
                <div className="mt-[var(--space-xs)] text-[var(--color-text-tertiary)]">
                  {failedId === b.character_id ? (
                    <span role="alert">{t('settings.blocked.unblockFailed', { name: b.display_name })}</span>
                  ) : (
                    t('settings.blocked.blockedOn', { date: formatDate(b.created_at) })
                  )}
                </div>
              </div>
              <button
                type="button"
                onClick={() => unblock(b.character_id)}
                className="btn-outline shrink-0 rounded-[var(--radius-md)]"
                style={CARD_CTA}
              >
                {t('settings.blocked.unblock')}
              </button>
            </li>
          ))}
        </ul>
      )}
    </SettingsCard>
  )
}
