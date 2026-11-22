import { useAuth } from '../auth/AuthContext'
import type { GameConfigOut } from '../api/gameConfig'
import { useGameConfig } from './useGameConfig'

/** Level at which the era unlocks an ability, read off the rung that lists it. */
export function levelWithUnlock(config: GameConfigOut | null, key: string): number | null {
  const level = config?.level_profiles.findIndex((p) =>
    p.unlocks.some((u) => u.kind === 'ability' && u.key === key),
  )
  return level == null || level < 0 ? null : level
}

export const commentLevelRequired = (config: GameConfigOut | null) =>
  levelWithUnlock(config, 'comment')

/** The level a signed-in viewer still needs to comment, or null (can comment / unknown). */
export function useCommentGate(): number | null {
  const { user } = useAuth()
  const level = commentLevelRequired(useGameConfig())
  return user?.character && !user.can_comment ? level : null
}
