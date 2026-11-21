// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import '../../../i18n'
import { OptionOverlay } from '../FilterBar/OptionPicker'

afterEach(cleanup)

it('opens the filter sheet on its first real control, not the scrim', () => {
  render(
    <OptionOverlay
      facet={{ key: 'k', label: 'Type', options: [{ value: 'a', label: 'A' }], selected: [], onChange: () => {} }}
      isSheet
      onDone={() => {}}
    />,
  )
  expect(document.activeElement).toBe(screen.getByRole('button', { name: /clear/i }))
})
