import { test, expect } from '@playwright/test'

// Guards e páginas de erro (WP-S5).

test('/conta redireciona para o login preservando o destino quando não autenticado', async ({ page }) => {
  await page.goto('/conta')
  await expect(page).toHaveURL(/\/entrar\?next=.*conta/)
})

test('uma rota inexistente renderiza a página de erro 404 (noindex) com saída para o cardápio', async ({ page }) => {
  const response = await page.goto('/rota-que-nao-existe-123')
  expect(response?.status()).toBe(404)
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/)
  await expect(page.getByRole('button', { name: 'Voltar ao cardápio' })).toBeVisible()
})

test('documento aplica a política de segurança da borda sem bloquear o app', async ({ request }) => {
  const response = await request.get('/menu', {
    headers: { 'x-forwarded-proto': 'https' }
  })
  const headers = response.headers()

  expect(response.status()).toBe(200)
  expect(headers['content-security-policy']).toContain("frame-ancestors 'none'")
  expect(headers['content-security-policy']).toContain('https://*.googleapis.com')
  expect(headers['permissions-policy']).toContain('geolocation=(self)')
  expect(headers['x-frame-options']).toBe('DENY')
  expect(headers['x-content-type-options']).toBe('nosniff')
  expect(headers['referrer-policy']).toBe('strict-origin-when-cross-origin')
  expect(headers['strict-transport-security']).toBe('max-age=31536000; includeSubDomains; preload')
})

test('home preserva o SSR e negocia compressão na origem', async ({ request }) => {
  const identity = await request.get('/', { headers: { 'accept-encoding': 'identity' } })
  const compressed = await request.get('/', { headers: { 'accept-encoding': 'gzip' } })
  const wildcard = await request.get('/', { headers: { 'accept-encoding': '*' } })
  const rejectedGzip = await request.get('/', { headers: { 'accept-encoding': 'gzip;q=0, *;q=1' } })
  const preferredIdentity = await request.get('/', { headers: { 'accept-encoding': 'gzip;q=0.5, identity;q=1' } })
  const rejectedAll = await request.get('/', { headers: { 'accept-encoding': 'gzip;q=0, identity;q=0, *;q=0' } })
  const head = await request.head('/', { headers: { 'accept-encoding': 'gzip' } })
  const cacheControl = compressed.headers()['cache-control']?.split(',').map(value => value.trim()) || []
  const vary = compressed.headers().vary?.split(',').map(value => value.trim().toLowerCase()) || []

  expect(compressed.status()).toBe(200)
  expect(cacheControl).toEqual(expect.arrayContaining(['private', 'no-transform']))
  expect(vary).toContain('accept-encoding')
  expect(compressed.headers()['content-encoding']).toBe('gzip')
  expect(Number(compressed.headers()['content-length'])).toBeGreaterThan(0)
  expect(Number(compressed.headers()['content-length'])).toBeLessThan(Number(identity.headers()['content-length']))
  expect(compressed.headers().etag).toBeUndefined()
  expect(wildcard.headers()['content-encoding']).toBe('gzip')
  expect(await compressed.text()).toBe(await identity.text())
  expect(await wildcard.text()).toBe(await identity.text())
  expect(identity.headers()['content-encoding']).toBeUndefined()
  expect(rejectedGzip.headers()['content-encoding']).toBeUndefined()
  expect(await rejectedGzip.text()).toBe(await identity.text())
  expect(preferredIdentity.headers()['content-encoding']).toBeUndefined()
  expect(await preferredIdentity.text()).toBe(await identity.text())
  expect(rejectedAll.status()).toBe(406)
  expect(await rejectedAll.text()).toBe('Not Acceptable')

  expect(head.status()).toBe(200)
  expect(head.headers()['content-encoding']).toBe('gzip')
  expect(head.headers()['content-length']).toBe(compressed.headers()['content-length'])
  expect(await head.body()).toHaveLength(0)
})
