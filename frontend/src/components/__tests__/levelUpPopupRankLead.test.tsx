/** The lead above the rank is per-rank, falling back to the shared lead. */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect } from 'vitest'
import i18n from '../../i18n'
import progression from '../../locales/en/progression.json'
import LevelUpPopup from '../LevelUpPopup'

const html = (rankKey: string) =>
  renderToStaticMarkup(<LevelUpPopup level={1} rankKey={rankKey} abilities={[]} onContinue={() => {}} />)

describe('LevelUpPopup rank lead', () => {
  it('an override on one rank changes only that rank', () => {
    i18n.addResource('en', 'progression', 'rankLead.ranger', 'Behold, a')
    try {
      expect(html('ranger')).toContain('Behold, a')
      expect(html('trailhead')).not.toContain('Behold, a')
      expect(html('trailhead')).toContain(progression.rankLead.trailhead)
    } finally {
      i18n.addResource('en', 'progression', 'rankLead.ranger', progression.rankLead.ranger)
    }
  })

  it('a rank without its own lead shows the shared lead', () => {
    i18n.addResource('en', 'progression', 'ranks.mystery', 'Mystery')
    expect(html('mystery')).toContain(progression.popup.levelReached)
  })
})
