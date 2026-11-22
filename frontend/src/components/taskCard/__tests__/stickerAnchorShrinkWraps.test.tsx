/** The corner-sticker anchor must hug the card on desktop (#4110). */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect } from 'vitest'
import '../../../i18n'
import TaskCard from '../TaskCard'
import { aTask } from '../../../test/fixtures'
import { readIndexCss } from '../../../test/indexCss'

describe('sticker anchor wrapper', () => {
  it('is the shrink-to-fit class, not a column-wide block', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <TaskCard task={aTask({ start_here: true })} basePoints={10} multiplier={1} />
      </MemoryRouter>,
    )
    expect(html.startsWith('<div class="task-fit-card"')).toBe(true)
  })

  it('.task-fit-card is fit-content, capped at the column, and the anchor', () => {
    const css = readIndexCss().replace(/\/\*[\s\S]*?\*\//g, '')
    const rule = /\.task-fit-card\s*\{([^}]*)\}/.exec(css)?.[1] ?? ''
    expect(rule).toMatch(/width:\s*fit-content/)
    expect(rule).toMatch(/max-width:\s*100%/)
    expect(rule).toMatch(/position:\s*relative/)
  })
})
