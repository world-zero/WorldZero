import { useEffect, useState } from 'react'
import { listBlocks } from '../api/relationships'
import { useAuth } from '../auth/AuthContext'

const NONE: ReadonlySet<number> = new Set()

/** Whom the viewer blocked (#3867): hide controls the server would refuse. */
export function useBlockedIds(enabled = true): ReadonlySet<number> {
  const { user } = useAuth()
  const characterId = user?.character?.id
  const [ids, setIds] = useState<ReadonlySet<number>>(NONE)
  useEffect(() => {
    if (!enabled || characterId == null) return
    let cancelled = false
    listBlocks()
      .then((blocks) => {
        if (!cancelled) setIds(new Set(blocks.map((block) => block.character_id)))
      })
      .catch(() => {
        // The control then shows and the server refuses it with CONTACT_BLOCKED.
      })
    return () => {
      cancelled = true
    }
  }, [enabled, characterId])
  return ids
}
