import { test, expect } from '@playwright/test'

// Resiliência do app independente de dados de negócio (WP-S5).

test('a home renderiza o shell mesmo com o backend vazio (degrada com dignidade)', async ({ page }) => {
  await page.goto('/')
  // O skip-link de acessibilidade é parte fixa do shell (app.vue).
  await expect(page.getByRole('link', { name: 'Pular para o conteúdo' })).toBeAttached()
  // A âncora de conteúdo principal existe.
  await expect(page.locator('#main-content')).toBeAttached()
})

test('o link de salto move o foco para o conteúdo principal', async ({ page }) => {
  await page.goto('/')
  const skipLink = page.getByRole('link', { name: 'Pular para o conteúdo' })
  const mainContent = page.locator('#main-content')

  await skipLink.focus()
  await skipLink.press('Enter')

  await expect(mainContent).toBeFocused()
})

test('o banner offline aparece ao perder conexão e some ao voltar', async ({ page, context }) => {
  await page.goto('/')

  await context.setOffline(true)
  const banner = page.getByTestId('offline-banner')
  await expect(banner).toBeVisible()
  await expect(banner).toContainText('Sem conexão')

  await context.setOffline(false)
  await expect(banner).toBeHidden()
})

test('uma navegação sem rede recebe o casco offline estático', async ({ page, context }) => {
  await page.goto('/')
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
  })

  await context.setOffline(true)
  await page.goto('/menu')

  await expect(page.getByRole('heading', { name: 'A loja ficou sem conexão' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Tentar de novo' })).toBeVisible()
})
