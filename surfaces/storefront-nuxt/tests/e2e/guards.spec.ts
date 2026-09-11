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
