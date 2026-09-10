import { test, expect } from '@playwright/test'
import { collectConsoleErrors, bodyText } from '../helpers'

// 01 — Smoke: superfícies renderizam, sem erro de console, guardas de rota ok.
test.describe('smoke — páginas e navegação', () => {
  test('home renderiza seções e sem erros de console', async ({ page }) => {
    const errors = collectConsoleErrors(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    await expect(page).toHaveTitle(/Nelson Boulangerie/)
    const body = await bodyText(page)
    // seções esperadas da home
    expect(body).toContain('Cardápio')
    expect(errors.filter(e => !e.includes('favicon'))).toEqual([])
  })

  test('menu renderiza categorias e produtos', async ({ page }) => {
    const errors = collectConsoleErrors(page)
    await page.goto('/menu', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    await expect(page.locator('h1')).toHaveText(/Cardápio/)
    const body = await bodyText(page)
    expect(body).toContain('Destaques')
    expect(body).toContain('Croissant')
    expect(errors).toEqual([])
  })

  test('PDP de produto existente renderiza dados e abas de informação', async ({ page }) => {
    const errors = collectConsoleErrors(page)
    await page.goto('/produto/CT', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2200)
    await expect(page.locator('h1').first()).toHaveText(/Croissant/)
    const body = await bodyText(page)
    expect(body).toContain('R$ 13,00')
    // abas informativas
    for (const tab of ['Ingredientes e restrições', 'Nutricional', 'Conservação']) {
      await page.locator('button').filter({ hasText: tab }).first().click()
      await page.waitForTimeout(400)
    }
    await expect(page.locator('button').filter({ hasText: /Ingredientes e restrições/i })).toBeVisible()
    expect(errors).toEqual([])
  })

  test('busca encontra produto conhecido', async ({ page }) => {
    const errors = collectConsoleErrors(page)
    await page.goto('/busca', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1800)
    const input = page.locator('input[type="search"], input[type="text"]').filter({ visible: true }).first()
    await input.fill('croissant')
    await page.waitForTimeout(2200)
    const body = await bodyText(page)
    expect(body).toContain('Croissant')
    expect(errors).toEqual([])
  })

  test('rota inexistente devolve 404 com UX de erro', async ({ page }) => {
    const errors = collectConsoleErrors(page)
    const res = await page.goto('/rota-que-nao-existe-xyz', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1500)
    expect(res?.status()).toBe(404)
    const body = await bodyText(page)
    expect(body.length).toBeGreaterThan(50) // página de erro renderizada, não tela branca
    expect(errors.filter(e => e.includes('404') === false)).toEqual([])
  })

  test('PDP inexistente devolve 404', async ({ page }) => {
    const res = await page.goto('/produto/SKU-NAO-EXISTE', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1500)
    expect(res?.status()).toBe(404)
  })

  test('termos e privacidade renderizam', async ({ page }) => {
    for (const route of ['/terms', '/privacy']) {
      const res = await page.goto(route, { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(1200)
      expect(res?.status()).toBe(200)
      expect((await bodyText(page)).length).toBeGreaterThan(100)
    }
  })
})
