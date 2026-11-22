import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../auth/AuthContext'
import { getMyCharacters } from '../api/me'

/**
 * Tells the player when the life they were carrying is gone and the server fell back
 * to a sibling (#4238 S8). A switch or a new life leaves the old one on the roster,
 * so only a missing roster entry counts.
 */
export default function LifeSwitchNotice() {
  const { user } = useAuth()
  const { t } = useTranslation('common')
  const [name, setName] = useState<string | null>(null)
  const character = user?.character ?? null
  // ponytail: in memory, so a reload forgets the carried life; a stored key would need cookie-card copy.
  const carried = useRef<number | null>(null)

  useEffect(() => {
    if (!character) return
    const previous = carried.current
    carried.current = character.id
    if (previous === null || previous === character.id) return
    let cancelled = false
    getMyCharacters()
      .then((lives) => {
        if (!cancelled && !lives.some((life) => life.id === previous)) {
          setName(character.display_name)
        }
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [character?.id, character?.display_name])

  if (name === null) return null
  return (
    <div
      role="status"
      className="fixed top-2 left-1/2 z-50 -translate-x-1/2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-[var(--color-text-primary)]"
    >
      {t('nowPlayingAs', { name })}{' '}
      <button type="button" className="underline" onClick={() => setName(null)}>
        {t('nowPlayingAsDismiss')}
      </button>
    </div>
  )
}
