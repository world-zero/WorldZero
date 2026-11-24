import { useNavigate } from 'react-router-dom'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { useTranslation } from 'react-i18next'
import PageTitle from '../components/ui/PageTitle'
import FactionSelectCard from '../components/selectCard/FactionSelectCard'
import type { SelectState } from '../components/selectCard/FactionSelectCard'
import { extractError } from '../utils/errors'
import { sortFactionsByRainbowOrder } from '../utils/factions'
import { useAuth } from '../auth/AuthContext'
import { useFormFactor } from '../hooks/useFormFactor'
import { useFactionsDirectory, type FactionsDirectoryState } from './factions/useFactionsDirectory'
import FactionSigil from '../components/sigil/FactionSigil'
import { ErrorBanner } from "../components/ui/ErrorBanner";

const NA_SLUG = 'na'

const STATUS_MEMBER = 'member'
const STATUS_INVITED = 'invited'
const STATUS_NOT_INVITED = 'not_invited'
const STATUS_DEFECTED = 'defected'
const STATUS_CAN_RETURN = 'can_return'

/**
 * Factions grid of preview tiles in rainbow order, one responsive page. All
 * membership actions live on `/factions/:slug` (#347).
 */
export default function Factions() {
  useDocumentTitle('Factions')
  return <FactionsDirectory state={useFactionsDirectory()} />
}

/** Exported for tests: the grid over a controlled state. */
export function FactionsDirectory({ state }: { state: FactionsDirectoryState }) {
  const { t } = useTranslation('factions')
  const { user } = useAuth()
  const navigate = useNavigate()
  // The phone's Community page already carries the title.
  const mobile = useFormFactor() === 'mobile'
  const character = user?.character ?? null
  const unaffiliated = !!character && (!character.faction_slug || character.faction_slug === NA_SLUG)

  const { factions, factionPage, loading } = state
  const error = state.error ? extractError(state.error, t('index.loadError')) : null

  const statusFor = (slug: string): string =>
    factionPage?.all_factions.find((f) => f.slug === slug)?.status ?? STATUS_NOT_INVITED

  if (loading) return <div className="py-8 font-body text-muted">{t('index.loading')}</div>

  const sortedFactions = sortFactionsByRainbowOrder(factions.filter((f) => f.slug !== NA_SLUG))

  // Status alone decides it: a held letter always implies member / can_return
  // / invited (#2310; status and letters share one select, #1384).
  const selectState = (slug: string): SelectState => {
    const status = statusFor(slug)
    if (status === STATUS_MEMBER) return 'member'
    if (status === STATUS_INVITED || status === STATUS_CAN_RETURN) return 'eligible'
    if (status === STATUS_DEFECTED) return 'burned'
    return 'locked'
  }

  return (
    <div className="py-8">
      {!mobile && <PageTitle title="Factions" />}

      {error && <ErrorBanner className="mb-4" message={error} />}

      {unaffiliated && (
        <section
          className="sidebar-card unaffiliated-banner mb-4"
        >
          <span aria-hidden="true" className="flex-none">
            <FactionSigil slug={NA_SLUG} size={34} />
          </span>
          <div>
            <div
              className="font-display italic unaffiliated-banner-title"
            >
              {t('mobile.unaffiliatedTitle')}
            </div>
            {/* Every clause is load-bearing (#1963): invitations are earned per
                faction (ADR-0022); the threshold is unnamed because it lives in
                EraConfig; delivery is passive. */}
            <p
              className="font-body unaffiliated-banner-body"
            >
              {t('mobile.unaffiliatedBody')}
            </p>
          </div>
        </section>
      )}

      {/* Stretch + column items (#3139) so a `SelectCardFrame` fills the row
          height and the calls line up along the bottom. */}
      <div
        data-testid="faction-tile-row"
        className="faction-tile-row justify-center md:justify-start"
      >
        {sortedFactions.map((f) => (
          <div
            key={f.slug}
            className="faction-tile"
            style={{ opacity: statusFor(f.slug) === STATUS_DEFECTED ? 0.5 : 1 }}
          >
            <FactionSelectCard
              faction={f.slug}
              state={selectState(f.slug)}
              onVisit={() => navigate(`/factions/${f.slug}`)}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
