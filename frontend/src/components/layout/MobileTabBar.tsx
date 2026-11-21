import { lazy, Suspense, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../auth/AuthContext'
import { useSidebarPanels } from '../../hooks/useSidebarPanels'
import FactionAvatar from '../avatar/FactionAvatar'
import PendingBadge from './PendingBadge'
import TabGlyph, { type GlyphName } from './tabGlyphs'
import { communityHref } from '../../pages/communitySide'
import './tabBar.css'

const YouSheet = lazy(() => import('./YouSheet'))
const ModTotal = lazy(() => import('../admin/ModTotal'))

type TabKey = 'nav.home' | 'nav.tasks' | 'nav.praxis' | 'nav.community'
const TABS: { glyph: GlyphName; key: TabKey; to: () => string; on: (path: string) => boolean }[] = [
  { glyph: 'home', key: 'nav.home', to: () => '/', on: (p) => p === '/' },
  { glyph: 'tasks', key: 'nav.tasks', to: () => '/tasks', on: (p) => p.startsWith('/tasks') },
  { glyph: 'praxis', key: 'nav.praxis', to: () => '/praxis', on: (p) => p.startsWith('/praxis') },
  {
    glyph: 'community',
    key: 'nav.community',
    to: communityHref,
    on: (p) => p.startsWith('/leaderboard') || p.startsWith('/factions'),
  },
]
const YOU_INDEX = TABS.length

/** Which tab is lit: the open You sheet wins over the route. */
export function activeTab(pathname: string, youOpen: boolean): number {
  return youOpen ? YOU_INDEX : TABS.findIndex((tab) => tab.on(pathname))
}

export default function MobileTabBar() {
  const { t } = useTranslation('common')
  const { pathname } = useLocation()
  const { user } = useAuth()
  const { pending_requests_count: pending } = useSidebarPanels()
  const [youOpen, setYouOpen] = useState(false)
  const [mod, setMod] = useState(0)
  const active = activeTab(pathname, youOpen)
  const character = user?.character ?? null
  const isAdmin = Boolean(user?.is_admin)
  const modCount = isAdmin ? mod : 0
  const badge = pending + modCount
  const youAria =
    badge === 0
      ? undefined
      : modCount === 0
        ? t('nav.youWithPending', { count: pending })
        : t('nav.youAdminLabel', {
            parts: [pending > 0 && t('nav.youPartRequests', { count: pending }), t('nav.youPartMod', { count: modCount })]
              .filter(Boolean)
              .join(', '),
          })

  const youLabel = t('nav.you')
  const youClass = 'tabbar__tab'
  const youInner = (
    <>
      <span className="tabbar__you">
        {character ? <FactionAvatar character={character} size={24} badge={false} /> : <span className="tabbar__guest" />}
        <PendingBadge count={badge} className="tabbar__badge" />
      </span>
      {youLabel}
    </>
  )

  return (
    <>
      <nav
        className="tabbar"
        aria-label={t('nav.primary')}
        style={{
          height: 'calc(var(--tab-bar-height) + env(safe-area-inset-bottom))',
          paddingBottom: 'env(safe-area-inset-bottom)',
        }}
      >
        <span
          aria-hidden="true"
          className="tabbar__hairline"
          hidden={active < 0}
          style={{ left: `calc(${active * 20 + 10}% - 14px)` }}
        />
        {TABS.map((tab, i) => (
          <Link
            key={tab.key}
            to={tab.to()}
            className="tabbar__tab"
            data-on={i === active ? '' : undefined}
            aria-current={i === active ? 'page' : undefined}
            onClick={() => setYouOpen(false)}
          >
            <TabGlyph name={tab.glyph} solid={i === active} />
            {t(tab.key)}
          </Link>
        ))}
        {!user ? (
          // The onboarding's sign-in view, the one sign-in screen (#1773).
          <Link to="/?login" className={youClass}>
            {youInner}
          </Link>
        ) : !character ? (
          <Link to="/characters/create" className={youClass}>
            {youInner}
          </Link>
        ) : (
          <button
            type="button"
            className={youClass}
            data-on={youOpen ? '' : undefined}
            aria-haspopup="dialog"
            aria-expanded={youOpen}
            aria-label={youAria}
            onClick={() => setYouOpen((o) => !o)}
          >
            {youInner}
          </button>
        )}
      </nav>
      {youOpen && character && (
        <Suspense fallback={null}>
          <YouSheet character={character} pending={pending} isAdmin={isAdmin} onClose={() => setYouOpen(false)} />
        </Suspense>
      )}
      {isAdmin && character && (
        <Suspense fallback={null}>
          <ModTotal onTotal={setMod} />
        </Suspense>
      )}
    </>
  )
}
