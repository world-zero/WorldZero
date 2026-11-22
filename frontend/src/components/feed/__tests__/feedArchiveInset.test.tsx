import type { ComponentType } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import CovenFeedFrame from '../CovenFeedFrame'
import DefaultFeedFrame from '../DefaultFeedFrame'
import EphemeristsFeedFrame from '../EphemeristsFeedFrame'
import EverymenFeedFrame from '../EverymenFeedFrame'
import SingularityFeedFrame from '../SingularityFeedFrame'
import SnideFeedFrame from '../SnideFeedFrame'
import UaFeedFrame from '../UaFeedFrame'
import WowFeedFrame from '../WowFeedFrame'
import type { FeedFrameProps } from '../feedFrameProps'
import '../../../i18n'
import { readIndexCss } from '../../../test/indexCss'

const css = readIndexCss()

// Frame -> the value its trailing band padding (or UA's margin) reads.
const PLACES: [string, ComponentType<FeedFrameProps>, string][] = [
  ['Default', DefaultFeedFrame, '--feed-archive-inset'],
  ['Singularity', SingularityFeedFrame, '--feed-archive-inset'],
  ['Ua', UaFeedFrame, '--feed-archive-inset'],
  ['Ephemerists', EphemeristsFeedFrame, '--feed-bar-pad'],
  ['Snide', SnideFeedFrame, '--feed-bar-pad'],
  ['Everymen', EverymenFeedFrame, '--feed-archive-inset'],
  ['Wow', WowFeedFrame, '--wow-head-pad'],
  ['Coven', CovenFeedFrame, '--coven-head-pad'],
]

describe('feed frames place the archive at one shared trailing inset', () => {
  it.each(PLACES)('%s frame reads the shared inset via %s', (_n, Frame, token) => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <Frame kicker="Task completed" time="2h ago" tag="Still waiting" archive={<span id="x" />}>
          <div />
        </Frame>
      </MemoryRouter>,
    )
    expect(html).toContain(`var(${token}`)
  })

  it.each([
    ['--feed-bar-pad', 1],
    ['--wow-head-pad', 2],
    ['--coven-head-pad', 2],
  ] as const)('%s routes its trailing inset through the token', (name, count) => {
    const decls = css.match(new RegExp(`${name}: [^;]*;`, 'g')) ?? []
    expect(decls).toHaveLength(count)
    for (const d of decls) expect(d).toContain('var(--feed-archive-inset)')
  })

  it('defines the token for desktop and phone', () => {
    expect(css.match(/--feed-archive-inset: var\(--space-(md|sm)\);/g)).toHaveLength(2)
  })
})
