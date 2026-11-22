/**
 * The level-up copy sheet (`/admin/level-ups`): the Field Stamp popup for every
 * level of the live era, for the copy editor. Like `FactionCopySheet`, no
 * editing mechanism of its own; Continue is a no-op.
 */
import { useTranslation } from 'react-i18next'
import PageTitle from '../../components/ui/PageTitle'
import LevelUpPopup from '../../components/LevelUpPopup'
import { useGameConfig } from '../../hooks/useGameConfig'
import { useFocusWithoutScroll } from './FactionCopySheet'
import { noop } from './copySheet/sheetFixtures'

export default function LevelUpCopySheet() {
  const { t } = useTranslation('admin')
  const { t: tp } = useTranslation('progression')
  const config = useGameConfig()
  useFocusWithoutScroll()
  return (
    <div className="py-8">
      <PageTitle title={t('levelUpSheet.title')} />
      <p className="card-meta mb-8">{t('levelUpSheet.intro')}</p>
      {/* Index 0 is the start state, never announced. */}
      {config?.level_profiles.map((profile, level) => level > 0 && (
        <section key={level} data-sheet-level={level} className="flex flex-col gap-3 mb-10">
          <h2 className="label-heading">{t('levelUpSheet.level', { level })}</h2>
          <div className="adm-levelup-frame">
            <LevelUpPopup
              level={level}
              rankKey={profile.rank_key}
              abilities={profile.unlocks}
              onContinue={noop}
              dimBackdrop={false}
              preview
            />
          </div>
        </section>
      ))}
      <section className="flex flex-col gap-3 mb-10">
        <h2 className="label-heading">{t('levelUpSheet.fallbackLead')}</h2>
        <p className="card-description">{tp('popup.levelReached')}</p>
      </section>
    </div>
  )
}
