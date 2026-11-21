import { useEffect } from 'react'
import { modTotal, useAdminCounts } from '../../pages/admin/useAdminCounts'

/** Lazy, admin-only: reads the mod queue for the tab bar's You badge so players never fetch it. */
export default function ModTotal({ onTotal }: { onTotal: (n: number) => void }) {
  const total = modTotal(useAdminCounts('you-tab'))
  useEffect(() => onTotal(total), [total, onTotal])
  return null
}
