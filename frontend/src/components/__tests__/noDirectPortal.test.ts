/** Overlays portal through `drawAtRoot` (#3894); a direct `createPortal` skips its document guard. */
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { it, expect } from 'vitest'

const SRC = join(__dirname, '..', '..')

function files(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? files(join(dir, e.name)) : /\.tsx?$/.test(e.name) ? [join(dir, e.name)] : [],
  )
}

it('only drawAtRoot imports createPortal', () => {
  const bad = files(SRC).filter(
    (f) =>
      !f.endsWith('drawAtRoot.ts') &&
      !f.includes('__tests__') &&
      /import[^;]*\bcreatePortal\b/.test(readFileSync(f, 'utf8')),
  )
  expect(bad).toEqual([])
})
