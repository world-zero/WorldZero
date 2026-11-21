import { test, expect } from '@playwright/test'

import { openTitle, passBeats } from './onboardingWalk'

/* #3835: on a phone the flow is edge to edge; nothing may widen the layout viewport (the old aurora made 375 read as 393). */
test.use({ storageState: { cookies: [], origins: [] }, viewport: { width: 375, height: 667 }, hasTouch: true, isMobile: true })

test('phone flow fills the screen: innerWidth 375 and no inset on every step', async ({ page }) => {
  test.setTimeout(120_000)
  const check = async () => {
    const r = await page.evaluate(() => {
      const b = document.querySelector<HTMLElement>('.ob-root')!.getBoundingClientRect()
      return { w: window.innerWidth, left: b.left, right: b.right, vw: document.documentElement.clientWidth }
    })
    expect(r).toEqual({ w: 375, left: 0, right: 375, vw: 375 })
  }
  await openTitle(page)
  await check()
  await page.getByTestId('onboarding-start').click()
  await passBeats(page, check)
})
