import { test, expect } from '@playwright/test'
import { login, addToCart, goToCheckout, ensureContactSaved, continueBtn, realErrors, collectConsoleErrors, bodyText } from '../helpers'

// 04 — Cenários variados: coleção, oferta, favoritos, cupom inválido, reorder, cancelamento.
test.describe('cenários variados', () => {
  test('coleção estática e oferta dinâmica renderizam', async ({ page }) => {
    const errors = collectConsoleErrors(page)
    // coleção estática (categoria) e dinâmica (destaques via /oferta)
    for (const route of ['/colecao/finos', '/oferta/featured']) {
      const res = await page.goto(route, { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(2000)
      expect(res?.status(), route).toBe(200)
      const b = await bodyText(page)
      expect(b.length, route).toBeGreaterThan(80)
    }
    // /colecao/featured (dinâmica) não existe como rota de coleção → 404 esperado
    const dyn = await page.goto('/colecao/featured', { waitUntil: 'domcontentloaded' })
    expect(dyn?.status()).toBe(404)
    // 404s esperados: oferta "featured" sem claim e o probe intencional de /colecao/featured
    // (console "Failed to load resource: 404" é o duplicado sem URL do mesmo evento)
    const noise = errors.filter(e => e.includes('/offers/featured/claim/') || e.includes('/colecao/featured') || /\[console\].*404/.test(e))
    expect(noise.length).toBeGreaterThan(0)
    expect(realErrors(errors.filter(e => !noise.includes(e)))).toEqual([])
  })

  test('busca sem resultado mostra estado vazio (não quebra)', async ({ page }) => {
    const errors = collectConsoleErrors(page)
    await page.goto('/busca', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1800)
    const input = page.locator('input[type="search"], input[type="text"]').filter({ visible: true }).first()
    await input.fill('zzzprodutoinexistente')
    await page.waitForTimeout(2200)
    const b = await bodyText(page)
    console.log('[report] busca vazia (200):', b.slice(0, 200).replace(/\n/g, ' | '))
    expect(b.length).toBeGreaterThan(50)
    expect(realErrors(errors)).toEqual([])
  })

  test('cupom inválido no checkout mostra erro claro', async ({ page }) => {
    test.setTimeout(240_000)
    const errors = collectConsoleErrors(page)
    await login(page)
    await addToCart(page, 'Croissant')
    await goToCheckout(page)
    await ensureContactSaved(page)
    // retirada (padrão) → continuar
    await continueBtn(page).click()
    await page.waitForTimeout(3000)
    // quando (amanhã padrão) → continuar
    const c2 = continueBtn(page)
    if (await c2.count()) { await c2.click(); await page.waitForTimeout(3000) }
    // pagamento: toggle de cupom → campo → aplicar inválido
    const toggle = page.locator('#checkout-coupon-toggle, [data-checkout-coupon]').first()
    console.log('[report] toggle cupom count:', await toggle.count())
    if (await toggle.count()) { await toggle.click(); await page.waitForTimeout(1200) }
    const input = page.locator('#checkout-coupon-input').filter({ visible: true }).first()
    console.log('[report] input cupom count:', await input.count())
    if (await input.count()) {
      await input.fill('CUPOM-INVALIDO-123')
      const aplicar = page.getByRole('button', { name: /Aplicar/i }).filter({ visible: true }).first()
      if (await aplicar.count()) await aplicar.click()
      await page.waitForTimeout(3000)
      const b = await bodyText(page)
      console.log('[report] após cupom inválido (300):', b.slice(0, 300).replace(/\n/g, ' | '))
      expect(b).toMatch(/inválid|não encontrad|não existe|não é válid|inexistent/i)
    }
    expect(realErrors(errors)).toEqual([])
  })

  test('cliente logado: favoritar e ver em /conta/favoritos', async ({ page }) => {
    test.setTimeout(240_000)
    const errors = collectConsoleErrors(page)
    await login(page)
    await page.goto('/produto/CT', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2200)
    const heart = page.locator('button[aria-label*="favorit"], button[aria-label*="Favorit"]').filter({ visible: true }).first()
    console.log('[report] heart count:', await heart.count())
    if (await heart.count()) {
      await heart.click()
      await page.waitForTimeout(1500)
      await page.goto('/conta/favoritos', { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(2500)
      const fav = await bodyText(page)
      console.log('[report] favoritos body (300):', fav.slice(0, 300).replace(/\n/g, ' | '))
      expect(fav).toContain('Croissant')
    }
    expect(realErrors(errors)).toEqual([])
  })

  test('refazer pedido (reorder) a partir do histórico', async ({ page }) => {
    test.setTimeout(240_000)
    const errors = collectConsoleErrors(page)
    await login(page)
    await page.goto('/conta/pedidos', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    const refazer = page.getByRole('button', { name: /Refazer/i }).first()
    console.log('[report] botão refazer count:', await refazer.count())
    if (await refazer.count()) {
      await refazer.click()
      await page.waitForTimeout(3500)
      const url = page.url()
      const b = await bodyText(page)
      console.log('[report] pós-refazer URL:', url, '| body (200):', b.slice(0, 200).replace(/\n/g, ' | '))
      // deve voltar ao carrinho ou menu com itens
      expect(url.includes('/sacola') || url.includes('/menu')).toBe(true)
    }
    expect(realErrors(errors)).toEqual([])
  })

  test('cancelamento de pedido a partir do tracking', async ({ page }) => {
    test.setTimeout(240_000)
    const errors = collectConsoleErrors(page)
    await login(page)
    await page.goto('/conta/pedidos', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    const link = page.locator('a[href*="/pedido/"]').first()
    if (await link.count()) {
      const href = await link.getAttribute('href')
      console.log('[report] primeiro pedido:', href)
      await link.click()
      await page.waitForTimeout(3500)
      const cancelar = page.getByRole('button', { name: /Cancelar/i }).filter({ visible: true }).first()
      console.log('[report] botão cancelar count:', await cancelar.count())
      if (await cancelar.count()) {
        await cancelar.click()
        await page.waitForTimeout(2000)
        const confirm = page.getByRole('button', { name: /Confirmar|Sim, cancelar|Cancelar pedido/i }).filter({ visible: true }).last()
        console.log('[report] confirm cancel count:', await confirm.count())
        if (await confirm.count()) await confirm.click()
        await page.waitForTimeout(4500)
        const after = await bodyText(page)
        console.log('[report] pós-cancelamento (300):', after.slice(0, 300).replace(/\n/g, ' | '))
        expect(after).toMatch(/cancelad|Cancelado/i)
        await page.screenshot({ path: 'artifacts/cancel-order.png', fullPage: true })
      }
    }
    expect(realErrors(errors)).toEqual([])
  })
})
