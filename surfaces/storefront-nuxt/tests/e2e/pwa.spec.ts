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
