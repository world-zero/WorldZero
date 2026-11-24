import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import { RosterAvatar } from '../RosterAvatar'

const draw = (over: { name: string; absent?: boolean; avatarUrl?: string }) =>
  renderToStaticMarkup(<RosterAvatar size={28} borderColor="red" {...over} />)

it('an absent side draws an empty circle, no letters and no portrait', () => {
  const html = draw({ name: '', absent: true, avatarUrl: '/x.png' })
  expect(html.replace(/<[^>]*>/g, '')).toBe('')
  expect(html).not.toContain('<img')
})

it('a present side still draws initials', () => {
  expect(draw({ name: 'Ada Lovelace' }).replace(/<[^>]*>/g, '')).toBe('AL')
})
