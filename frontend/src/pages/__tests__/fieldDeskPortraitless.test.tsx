// @vitest-environment jsdom
/** Seam: FieldDesk (desktop) — a portrait-less life draws its username initial in the pill and the roster card, not an empty disc (#3797). */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import '../../i18n'
import type { CharacterOut } from '../../api/auth'

const life = {
  id: 7, username: 'wren', display_name: 'Ash', faction_slug: 'coven', avatar_url: null, level: 2, score: 0,
} as unknown as CharacterOut

vi.mock('../../hooks/useFormFactor', () => ({ useFormFactor: () => 'desktop' }))
vi.mock('../../auth/AuthContext', () => ({
  useAuth: () => ({ user: { character: life, can_create_additional_character: true }, applyUser: () => {} }),
}))
vi.mock('../../api/me', () => ({ getMyCharacters: async () => [life], setActiveCharacter: async () => ({}) }))
vi.mock('../../api/tasks', () => ({ listTasks: async () => [] }))
vi.mock('../../api/praxis', () => ({ listPraxes: async () => [] }))
vi.mock('../../hooks/useSidebarPanels', () => ({ useSidebarPanels: () => ({ active_praxes: [] }) }))
vi.mock('../fieldDesk/useFieldDeskHome', () => ({ useFieldDeskHome: () => null }))

import FieldDesk from '../FieldDesk'

it('pill and roster card both show the username initial', async () => {
  render(<MemoryRouter><FieldDesk /></MemoryRouter>)
  await screen.findAllByText(/@wren/)
  expect(screen.getAllByText('W').length).toBeGreaterThanOrEqual(2)
  expect(screen.queryByText('A')).toBeNull()
})
