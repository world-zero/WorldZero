// @vitest-environment jsdom
/** A push or feed row deep-links `#comment-{id}`; the thread scrolls there once its rows exist. */
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import '../../../i18n'
import type { CommentOut } from '../../../api/comments'
import CommentThread from '../CommentThread'

const COMMENT: CommentOut = {
  id: 7,
  praxis_id: 1,
  task_id: null,
  admin_note: null,
  is_censored: false,
  body_text: 'seedlings along the estuary',
  is_edited: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  author: { name_state: 'ok', id: 42, username: 'ada', display_name: 'Adabel', avatar_url: '', faction_slug: 'na' },
  mentions: [],
}

describe('CommentThread deep link', () => {
  it('scrolls the linked comment into view', () => {
    const scrolled: Element[] = []
    Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
      scrolled.push(this)
    })
    render(
      <MemoryRouter initialEntries={['/praxis/1#comment-7']}>
        <CommentThread target="praxes" targetId={1} seed={[COMMENT]} />
      </MemoryRouter>,
    )
    expect(scrolled.map((el) => el.id)).toEqual(['comment-7'])
  })
})
