import { Link, NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { AdminCounts } from '../../pages/admin/useAdminCounts'
import { useCan, type Need } from '../../auth/permissions'

type Badge = 'urgent' | 'quiet'
type ItemKey = 'era' | 'reports' | 'messages' | 'proposals' | 'praxis' | 'tasks' | 'people' | 'smallWorld' | 'modLog' | 'factionCopy' | 'levelCopy' | 'tauntCopy' | 'copyProposals'
type GroupKey = 'needs' | 'run' | 'words'
interface Item {
  key: ItemKey
  to: string
  count?: keyof AdminCounts
  badge?: Badge
  tally?: keyof AdminCounts
  need?: Need
}

const GROUPS: { key: GroupKey; items: Item[] }[] = [
  {
    key: 'needs',
    items: [
      { key: 'reports', to: '/admin/reports', count: 'reports', badge: 'urgent' },
      { key: 'messages', to: '/admin/messages', count: 'messages', badge: 'quiet' },
      { key: 'proposals', to: '/admin/proposals', count: 'proposals', badge: 'quiet' },
    ],
  },
  {
    key: 'run',
    items: [
      { key: 'praxis', to: '/admin/praxis', tally: 'praxis' },
      { key: 'tasks', to: '/admin/tasks', tally: 'tasks' },
      { key: 'people', to: '/admin/people', tally: 'people' },
      { key: 'smallWorld', to: '/admin/small-world' },
      { key: 'modLog', to: '/admin/mod-log' },
    ],
  },
  {
    key: 'words',
    items: [
      { key: 'factionCopy', to: '/admin/copy', need: 'copy' },
      { key: 'levelCopy', to: '/admin/level-ups', need: 'copy' },
      { key: 'tauntCopy', to: '/admin/taunts', need: 'copy' },
      { key: 'copyProposals', to: '/admin/copy-proposals', need: 'copy' },
    ],
  },
]

const ERA: Item = { key: 'era', to: '/admin/era' }

const ALL = [...GROUPS.flatMap((g) => g.items), ERA]

/** Every other item's key names its own entry in `NEEDS`. */
export const needOf = (item: Item): Need => item.need ?? (item.key as Need)

/** The rail item for a path (sub-pages like /admin/copy/ua belong to their parent), so the phone bar can title itself. */
export function itemAt(pathname: string): Item | undefined {
  return ALL.find((i) => pathname === i.to || pathname.startsWith(`${i.to}/`))
}

/** Where `/admin` lands: the first page the caller may open (the mod log is open to every admin). */
export const firstAllowed = (can: (need: Need) => boolean): string => ALL.find((i) => can(needOf(i)))!.to

/** The console's left rail. `onNavigate` lets the phone Menu close itself. */
export default function AdminRail({
  open,
  onNavigate,
  counts,
}: {
  open: boolean
  onNavigate: () => void
  counts: AdminCounts
}) {
  const { t } = useTranslation('admin')
  const can = useCan()
  const groups = GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => can(needOf(i))) })).filter((g) => g.items.length > 0)

  return (
    <nav id="admin-rail" className="adm-rail" aria-label={t('console.rail.label')} data-open={open} onClick={onNavigate}>
      <Link to="/" className="adm-back">
        {t('console.rail.back')}
      </Link>
      <div className="adm-brand">
        <span className="adm-word">{t('console.rail.brand')}</span>
        <span className="adm-spectrum" aria-hidden="true" />
        <span className="card-meta">{t('console.rail.sub')}</span>
      </div>
      {groups.map((group) => (
        <div key={group.key}>
          <p className="adm-grp">{t(`console.rail.groups.${group.key}`)}</p>
          {group.items.map((item) => {
            const count = item.count ? counts[item.count] : null
            const tally = item.tally ? counts[item.tally] : null
            return (
              <NavLink key={item.key} to={item.to} className="adm-nav">
                <span>{t(`console.rail.items.${item.key}`)}</span>
                {count ? (
                  <span
                    className={item.badge === 'quiet' ? 'adm-count adm-count-q' : 'adm-count'}
                    aria-label={t('console.rail.countLabel', { count })}
                  >
                    {count}
                  </span>
                ) : null}
                {tally !== null && <span className="adm-tally">{tally}</span>}
              </NavLink>
            )
          })}
        </div>
      ))}
      <div className="adm-fill" />
      {can(needOf(ERA)) && (
        <>
          <hr className="adm-rule" />
          <p className="adm-grp adm-grp-danger">{t('console.rail.groups.danger')}</p>
          <NavLink to={ERA.to} className="adm-nav adm-nav-danger">
            <span>{t('console.rail.items.era')}</span>
          </NavLink>
        </>
      )}
    </nav>
  )
}
