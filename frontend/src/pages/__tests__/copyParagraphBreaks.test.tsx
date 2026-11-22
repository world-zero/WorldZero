import { renderToStaticMarkup } from 'react-dom/server'
import { describe, it, expect } from 'vitest'
import i18n from '../../i18n'
import AiPolicy from '../AiPolicy'
import Attributions from '../Attributions'

const PARAGRAPH = /<p class="[^"]*whitespace-pre-line[^"]*">first\n\nsecond<\/p>/g

describe('owner copy keeps its paragraph breaks', () => {
  it.each([
    ['AiPolicy', AiPolicy, ['ai.built', 'ai.praxis']],
    ['Attributions', Attributions, ['attributions.intro']],
  ] as const)('%s renders \\n inside a pre-line paragraph', (_name, Page, keys) => {
    for (const k of keys) i18n.addResource('en', 'common', k, 'first\n\nsecond')
    const html = renderToStaticMarkup(<Page />)
    expect(html.match(PARAGRAPH)).toHaveLength(keys.length)
  })
})
