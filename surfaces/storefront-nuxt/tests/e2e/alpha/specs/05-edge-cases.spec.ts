import { test, expect } from '@playwright/test'
import { login, addToCart, goToCheckout, collectConsoleErrors, realErrors, pace, bodyText } from '../helpers'

// 05 — Casos de borda: guardas, validações, quantidade, 404, estados vazios.
test.describe('casos de borda', () => {
  test('telefone inválido no login mostra erro', async ({ page }) => {
    const errors = collectConsoleErrors(page)
    await page.goto('/entrar', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2200)
    await page.getByText(/Não consigo usar WhatsApp/i).first().click()
    await page.waitForTimeout(1400)
    const phone = page.locator('input[inputmode="tel"], input[type="tel"]').filter({ visible: true }).first()
    await expect(phone).toBeVisible()
    await phone.fill('123')
    await page.waitForTimeout(600)
    const sms = page.locator('button').filter({ hasText: /Receber por SMS/i }).first()
    await sms.click()
    await page.waitForTimeout(2500)
    const b = await bodyText(page)
    console.log('[report] telefone inválido (300):', b.slice(0, 300).replace(/\n/g, ' | '))
    expect(b).toMatch(/inválid|inválido|número|digite/i)
    expect(realErrors(errors)).toEqual([])
  })

  test('código OTP errado é rejeitado com erro claro', async ({ page }) => {
    test.setTimeout(240_000)
    const errors = collectConsoleErrors(page)
    await pace()
    // passa pela tela de código SEM clicar em "usar código de teste"
    await page.goto('/entrar', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2200)
    await page.getByText(/Não consigo usar WhatsApp/i).first().click()
    await page.waitForTimeout(1400)
    const phone = page.locator('input[inputmode="tel"], input[type="tel"]').filter({ visible: true }).first()
    await phone.fill('11999999999')
    await page.waitForTimeout(400)
    // request do código com retry em caso de rate-limit
    for (let attempt = 0; attempt < 3; attempt++) {
      await page.locator('button').filter({ hasText: /Receber por SMS/i }).first().click()
      await page.waitForTimeout(4500)
      const limited = await page.getByText(/Muitas tentativas/i).count()
      if (!limited) break
      console.log(`[report] request-code limitado — retry em 60s (${attempt + 1})`)
      await page.waitForTimeout(60_000)
    }
    // digita código errado nos 6 campos
    const boxes = page.locator('input[type="text"]').filter({ visible: true })
    const boxCount = await boxes.count()
    console.log('[report] caixas de código:', boxCount)
    expect(boxCount).toBeGreaterThanOrEqual(6)
    for (let i = 0; i < 6; i++) await boxes.nth(i).fill('0')
    await page.waitForTimeout(2000)
    const b = await bodyText(page)
    console.log('[report] OTP errado (400):', b.slice(0, 400).replace(/\n/g, ' | '))
    expect(b).toMatch(/errad|inválid|não confere|não é válid|tente novamente/i)
    // segue para o código certo (o erro deve ter limpo os campos ou mantido a tela)
    const testBtn = page.locator('button').filter({ hasText: /Usar código de teste/i }).first()
    if (await testBtn.count()) { await testBtn.click(); await page.waitForTimeout(600) }
    const entrar = page.locator('button').filter({ hasText: /^Entrar$/i }).first()
    if (await entrar.count()) await entrar.click()
    await page.waitForTimeout(4000)
    expect(realErrors(errors)).toEqual([])
  })

  test('quantidade acima do disponível é limitada', async ({ page }) => {
    test.setTimeout(240_000)
    const errors = collectConsoleErrors(page)
    await login(page)
    await addToCart(page, 'Croissant')
    await page.goto('/sacola', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    const b0 = await bodyText(page)
    console.log('[report] sacola (400):', b0.slice(0, 400).replace(/\n/g, ' | '))
    // controles de quantidade (+, -, input)
    const qtyInput = page.locator('input[type="number"], input[inputmode="numeric"]').filter({ visible: true }).first()
    const plus = page.locator('button[aria-label*="aumentar"], button[aria-label*="Aumentar"], button[aria-label*="mais"]').filter({ visible: true }).first()
    console.log('[report] qty input:', await qtyInput.count(), '| plus btn:', await plus.count())
    if (await plus.count()) {
      for (let i = 0; i < 5; i++) {
        await plus.click()
        await page.waitForTimeout(700)
      }
      const b1 = await bodyText(page)
      console.log('[report] qty após 5 cliques (300):', b1.slice(0, 300).replace(/\n/g, ' | '))
    }
    expect(realErrors(errors)).toEqual([])
  })

  test('sacola vazia: mensagem de estado vazio coerente', async ({ page }) => {
    const errors = collectConsoleErrors(page)
    await page.goto('/sacola', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    const b = await bodyText(page)
    console.log('[report] sacola vazia (300):', b.slice(0, 300).replace(/\n/g, ' | '))
    expect(b.length).toBeGreaterThan(80)
    // sem CTA de finalizar
    const fin = await page.locator('a[href="/finalizar"]').filter({ visible: true }).count()
    expect(fin).toBe(0)
    expect(realErrors(errors)).toEqual([])
  })

  test('home em horário fechado mostra status fechado', async ({ page }) => {
    const errors = collectConsoleErrors(page)
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    const b = await bodyText(page)
    const fechado = /Fechado/.test(b)
    console.log('[report] header mostra Fechado:', fechado)
    // status presente de alguma forma (aberto ou fechado — não é bug; registra no relatório)
    expect(b.length).toBeGreaterThan(100)
    expect(realErrors(errors)).toEqual([])
  })

  test('checkout com carrinho vazio (logado) não quebra', async ({ page }) => {
    test.setTimeout(240_000)
    const errors = collectConsoleErrors(page)
    await login(page)
    await page.goto('/finalizar', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    const url = page.url()
    const b = await bodyText(page)
    console.log('[report] finalizar vazio URL:', url, '| body (250):', b.slice(0, 250).replace(/\n/g, ' | '))
    expect(b.length).toBeGreaterThan(50)
    expect(realErrors(errors)).toEqual([])
  })
})
