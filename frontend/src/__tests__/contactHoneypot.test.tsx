import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect } from 'vitest'

import '../i18n'
import Contact from '../pages/Contact'

describe('Contact honeypot', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <Contact />
    </MemoryRouter>,
  )
  const wrapper = html.match(/<div aria-hidden="true"[^>]*>(.*?)<\/div>/)?.[1] ?? ''

  it('is hidden from screen readers and the keyboard', () => {
    expect(wrapper).toContain('name="website"')
    expect(wrapper).toContain('tabindex="-1"')
    expect(wrapper).toContain('autoComplete="off"')
  })

  it('leaves the real fields reachable', () => {
    expect(html).toContain('name="message"')
    expect(html).toContain('type="submit"')
  })
})
