import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import { panelStyle } from './Sidebar'

/**
 * The one control that folds the desktop rail away and back (#1191): same
 * handle in both states, styled from the rail's `panelStyle`. It carries no
 * pending badge (#4131): the NavBar's Updates link is where desktop shows it.
 */
const handleStyle: CSSProperties = {
  ...panelStyle,
  // panelStyle's --space-lg would swallow a 32px-wide control whole.
  padding: 'var(--space-xs)',
  // Chrome, not a rail sheet (#2404): keeps the generic card radius.
  borderRadius: 'var(--radius-xl)',
  color: 'var(--color-text-secondary)',
  fontSize: 'var(--text-content)',
  lineHeight: 1,
  cursor: 'pointer',
}

export default function SidebarHandle({
  collapsed,
  onToggle,
}: {
  readonly collapsed: boolean
  readonly onToggle: () => void
}) {
  const { t } = useTranslation('common')
  const label = collapsed ? t('sidebar.toggle.expand') : t('sidebar.toggle.collapse')

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={!collapsed}
      // The rail stays mounted (#1343), so this id always resolves.
      aria-controls="wz-sidebar"
      aria-label={label}
      title={label}
      className="flex items-center justify-center w-8 mb-4"
      style={handleStyle}
    >
      {/* An SVG, not a text glyph: a guillemet's ink sits low in its em box (#4117). */}
      <svg
        aria-hidden="true"
        viewBox="0 0 12 12"
        width="1em"
        height="1em"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{ display: 'block', transform: collapsed ? 'scaleX(-1)' : undefined }}
      >
        <path d="M8 2 4 6l4 4" />
      </svg>
    </button>
  )
}
