import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import MarkdownPreview from '../editPraxis/blocks/MarkdownPreview'
import { PraxisExcerpt } from '../../components/praxisCard/shared'
import type { PraxisCardOut } from '../../api/praxis'

// react-markdown emits "\n" between blocks, which body's pre-line would draw; `.md-flow` opts out.
it('markdown renderers opt out of the app-wide pre-line with md-flow', () => {
  expect(renderToStaticMarkup(<MarkdownPreview source={'a\n\nb'} />)).toMatch(/^<div class="md-flow">/)
  const excerpt = renderToStaticMarkup(<PraxisExcerpt praxis={{ body_text: 'a\n\nb' } as PraxisCardOut} />)
  expect(excerpt).toMatch(/^<p class="[^"]*\bmd-flow\b/)
})
