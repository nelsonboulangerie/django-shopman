import { expect, test } from '@playwright/test'

test('manifesto, service worker e metadados iOS são servidos pelo build', async ({ page, request }) => {
  const manifestResponse = await request.get('/manifest.webmanifest')
  expect(manifestResponse.ok()).toBe(true)
  expect(manifestResponse.headers()['content-type']).toContain('application/manifest+json')
  expect(manifestResponse.headers()['cache-control']).toBe('public, max-age=3600')

  const manifest = await manifestResponse.json()
  expect(manifest.icons).toEqual(expect.arrayContaining([
    expect.objectContaining({ sizes: '512x512', purpose: 'maskable' }),
    expect.objectContaining({ sizes: '512x512', purpose: 'monochrome' })
  ]))
  expect(manifest.screenshots).toHaveLength(3)

  const workerResponse = await request.head('/sw.js')
  expect(workerResponse.ok()).toBe(true)
  expect(workerResponse.headers()['cache-control']).toBe('no-cache, no-store, must-revalidate')

  await page.goto('/')
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href', '/manifest.webmanifest')
  await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute('href', '/pwa/apple-touch-icon-180x180.png')
  await expect(page.locator('link[rel="apple-touch-startup-image"]')).toHaveCount(40)
})

test('service worker registra e entrega o casco quando uma navegação perde a rede', async ({ page, context }) => {
  await page.goto('/')
  await page.evaluate(async () => navigator.serviceWorker.ready)

  await context.setOffline(true)
  await page.goto('/menu')

  await expect(page.getByRole('heading', { name: 'A loja ficou sem conexão' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Tentar de novo' })).toBeVisible()
})

test('convite de instalação não aparece no checkout', async ({ page }) => {
  await page.goto('/finalizar')
  await page.evaluate(() => {
    const event = new Event('beforeinstallprompt', { cancelable: true })
    Object.defineProperties(event, {
      prompt: { value: async () => undefined },
      userChoice: { value: Promise.resolve({ outcome: 'dismissed', platform: 'web' }) }
    })
    window.dispatchEvent(event)
  })

  await expect(page.getByTestId('pwa-install-invite')).toBeHidden()
})

test('overlays travam e restauram o body no navegador comum', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/menu')

  const body = page.locator('body')
  const viewport = page.locator('[data-shop-scroll-viewport]')
  await page.getByRole('button', { name: 'Abrir menu' }).click()

  await expect.poll(() => body.evaluate(element => element.style.overflow)).toBe('hidden')
  expect(await viewport.evaluate(element => element.style.overflow)).not.toBe('hidden')

  await page.getByRole('button', { name: 'Fechar menu' }).click()
  await expect.poll(() => body.evaluate(element => element.style.overflow)).toBe('')
})

test('barra inferior permanece ancorada fora da rolagem no PWA instalado', async ({ page }) => {
  await page.addInitScript(() => {
    const nativeMatchMedia = window.matchMedia.bind(window)
    Object.defineProperty(navigator, 'maxTouchPoints', { configurable: true, get: () => 5 })
    window.matchMedia = query => query === '(display-mode: standalone)'
      ? {
          matches: true,
          media: query,
          onchange: null,
          addListener: () => undefined,
          removeListener: () => undefined,
          addEventListener: () => undefined,
          removeEventListener: () => undefined,
          dispatchEvent: () => true
        }
      : nativeMatchMedia(query)
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/menu')

  await expect(page.locator('html')).toHaveClass(/shop-ios-standalone/)
  await page.locator('#main-content').evaluate(element => {
    const filler = document.createElement('div')
    filler.style.height = '3000px'
    filler.dataset.testScrollFiller = ''
    element.appendChild(filler)
  })

  const viewport = page.locator('[data-shop-scroll-viewport]')
  const bottomNav = page.locator('.shop-bottomnav-bar')
  await expect(viewport).toHaveCSS('overflow-y', 'auto')
  await expect(bottomNav).toHaveCSS('position', 'relative')

  const shellColors = await page.evaluate(() => {
    const viewport = document.querySelector<HTMLElement>('[data-shop-scroll-viewport]')!
    const main = document.querySelector<HTMLElement>('#main-content')!
    const probe = document.createElement('div')
    probe.style.backgroundColor = 'var(--shop-ink)'
    document.body.appendChild(probe)
    const ink = getComputedStyle(probe).backgroundColor
    probe.style.backgroundColor = 'var(--background)'
    const canvas = getComputedStyle(probe).backgroundColor
    probe.remove()
    return {
      canvas,
      ink,
      main: getComputedStyle(main).backgroundColor,
      shell: getComputedStyle(document.querySelector<HTMLElement>('.shop-shell')!).backgroundColor,
      viewport: getComputedStyle(viewport).backgroundColor
    }
  })
  expect(shellColors.ink).not.toBe(shellColors.canvas)
  expect(shellColors.shell).toBe(shellColors.ink)
  expect(shellColors.viewport).toBe(shellColors.ink)
  expect(shellColors.main).toBe(shellColors.canvas)

  const contentFlow = await page.evaluate(() => {
    const main = document.querySelector<HTMLElement>('#main-content')!
    const filler = document.querySelector<HTMLElement>('[data-test-scroll-filler]')!
    const footer = document.querySelector<HTMLElement>('.shop-footer')!
    return {
      mainClientHeight: main.clientHeight,
      mainScrollHeight: main.scrollHeight,
      fillerBottom: filler.getBoundingClientRect().bottom,
      footerTop: footer.getBoundingClientRect().top
    }
  })
  expect(contentFlow.mainClientHeight).toBe(contentFlow.mainScrollHeight)
  expect(contentFlow.footerTop).toBeGreaterThanOrEqual(contentFlow.fillerBottom)

  const before = await bottomNav.boundingBox()
  await viewport.evaluate(element => element.scrollTo({ top: 900, behavior: 'instant' }))
  await expect.poll(() => viewport.evaluate(element => element.scrollTop)).toBe(900)
  const after = await bottomNav.boundingBox()

  expect(before).not.toBeNull()
  expect(after).not.toBeNull()
  expect(after?.y).toBeCloseTo(before?.y || 0, 0)
  expect((after?.y || 0) + (after?.height || 0)).toBeCloseTo(844, 0)
  expect(await page.evaluate(() => window.scrollY)).toBe(0)

  await bottomNav.getByRole('link', { name: 'Início' }).click()
  await expect(page).toHaveURL('/')
  await expect.poll(() => viewport.evaluate(element => element.scrollTop)).toBe(0)

  const body = page.locator('body')
  await page.getByRole('button', { name: 'Abrir menu' }).click()
  await expect.poll(() => viewport.evaluate(element => element.style.overflow)).toBe('hidden')
  expect(await body.evaluate(element => element.style.overflow)).not.toBe('hidden')

  await page.getByRole('button', { name: 'Fechar menu' }).click()
  await expect.poll(() => viewport.evaluate(element => element.style.overflow)).toBe('')
})
