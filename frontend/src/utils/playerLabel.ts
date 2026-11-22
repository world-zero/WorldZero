import i18n from '../i18n'
import type { components } from '../api/generated/schema'

type NameState = components['schemas']['NameState']

/** Non-hook twin of `usePlayerLabel`, for code that builds rows outside a component (#4238). */
export function playerLabel(name: string, state: NameState): string {
  if (state === 'absent') return i18n.t('common:absentPlayer')
  if (state === 'suspended') return i18n.t('common:suspendedPlayer', { name })
  return name
}
