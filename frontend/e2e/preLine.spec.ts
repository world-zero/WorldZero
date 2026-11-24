import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

// #4293: copy keeps its line breaks app-wide; markdown containers opt out with .md-flow.
test('the app root keeps line breaks and .md-flow resets them', async ({ page }) => {
  await page.goto('/about')
  await expect(page.locator('#root')).toHaveCSS('white-space', 'pre-line')
  await page.evaluate(() => {
    const el = document.createElement('div')
    el.className = 'md-flow'
    el.id = 'probe-md-flow'
    document.getElementById('root')!.appendChild(el)
  })
  await expect(page.locator('#probe-md-flow')).toHaveCSS('white-space', 'normal')
})
