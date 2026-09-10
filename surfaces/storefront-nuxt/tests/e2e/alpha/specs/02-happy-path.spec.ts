import { test, expect } from '@playwright/test'
import { login, addToCart, goToCheckout, ensureContactSaved, collectConsoleErrors, realErrors, bodyText, TEST_NAME } from '../helpers'

// 02 — Caminho feliz ponta a ponta: login → menu → carrinho → checkout (retirada) → pagamento → tracking.
// Obs.: execução em horário fechado (18h+) — o fluxo de "encomendar" segue válido; o relatório registra.
test.describe('caminho feliz — pedido de retirada completo', () => {
  test('login → adicionar 2 itens → checkout retirada → pix → tracking confirmado', async ({ page }) => {
    const errors = collectConsoleErrors(page)
    test.setTimeout(240_000)

    // 1) login
    await login(page)
    await page.goto('/conta', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    expect(page.url()).toContain('/conta')

    // 2) adicionar itens pelo menu
    await addToCart(page, 'Croissant')
    await addToCart(page, 'Café Coado')

    // 3) sacola: conferir itens e totais
    await page.goto('/sacola', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    const sacola = await bodyText(page)
    expect(sacola).toContain('Croissant')
    expect(sacola).toContain('Café Coado')
    const totalMatch = sacola.match(/R\$ (\d+,\d{2})/)
    console.log('[report] total sacola:', totalMatch?.[1])

    // 4) checkout
    await goToCheckout(page)
    expect(page.url()).toContain('/finalizar')

    // passo Contato: nome + SALVAR contato (pode vir pré-salvo do perfil)
    await ensureContactSaved(page, TEST_NAME)

    // passo Como receber: Retirada já é o padrão → Continuar
    const body2 = await bodyText(page)
    expect(body2).toMatch(/Retirada|Entrega/)
    const retRadio = page.getByRole('radio', { name: /Retirada/i }).first()
    if (await retRadio.count()) {
      const checked = await retRadio.isChecked().catch(() => false)
      console.log('[report] retirada checked:', checked)
      expect(checked, 'Retirada deveria vir marcada por padrão').toBe(true)
    }
    const continuar = page.getByRole('button', { name: /^Continuar$/i }).first()
    await expect(continuar).toBeVisible({ timeout: 10_000 })
    await continuar.click()
    await page.waitForTimeout(3500)

    // passo Quando: exibe opção de data (amanhã) → Continuar
    const body3 = await bodyText(page)
    console.log('[report] passo quando (250):', body3.slice(0, 250).replace(/\n/g, ' | '))
    expect(body3).toMatch(/Amanhã|amanhã|Escolha|Quando/)
    const quandoNext = page.getByRole('button', { name: /^Continuar$/i }).first()
    if (await quandoNext.count()) { await quandoNext.click(); await page.waitForTimeout(3500) }

    // passo Pagamento: Pix
    const body4 = await bodyText(page)
    console.log('[report] passo pagamento (250):', body4.slice(0, 250).replace(/\n/g, ' | '))
    const pixRadio = page.getByRole('radio', { name: /Pix/i }).first()
    if (await pixRadio.count()) {
      const pixChecked = await pixRadio.isChecked().catch(() => false)
      console.log('[report] pix checked:', pixChecked)
      if (!pixChecked) await pixRadio.click()
    }
    await page.waitForTimeout(800)

    // revisão: botão "Revisar pedido" abre o sheet de confirmação
    const revisar = page.getByRole('button', { name: /Revisar pedido/i }).filter({ visible: true }).first()
    await expect(revisar).toBeVisible({ timeout: 10_000 })
    await revisar.click()
    await page.waitForTimeout(2500)
    const sheet = page.getByRole('dialog').filter({ hasText: /Revise seu pedido/i }).first()
    await expect(sheet).toBeVisible({ timeout: 10_000 })
    await page.screenshot({ path: 'artifacts/happy-review-sheet.png', fullPage: true })
    const sheetBody = await sheet.innerText()
    console.log('[report] sheet revisão (400):', sheetBody.slice(0, 400).replace(/\n/g, ' | '))

    // confirmação: botão principal do sheet (label dinâmico do checkout action)
    const confirmar = sheet.getByRole('button').filter({ hasText: /Enviar|Confirmar/i }).last()
    await expect(confirmar).toBeVisible({ timeout: 10_000 })
    console.log('[report] CTA confirmação:', (await confirmar.innerText()).trim())
    await confirmar.click()
    await page.waitForTimeout(8000)

    // 5) tracking: pedido criado com ref
    const url = page.url()
    console.log('[report] URL pós-envio:', url)
    const refMatch = url.match(/\/pedido\/([^/]+)/)
    expect(refMatch, `URL deveria conter ref do pedido: ${url}`).not.toBeNull()
    const ref = refMatch![1]
    console.log('[report] ORDER_REF=' + ref)
    const trackBody = await bodyText(page)
    expect(trackBody.length).toBeGreaterThan(100)
    await page.screenshot({ path: `artifacts/happy-tracking-${ref}.png`, fullPage: true })

    // 6) pagamento: block de pagamento presente (mock habilitado em staging) → pagar
    const payBtn = page.locator('button').filter({ hasText: /Pagar|Pix|pagar/i }).filter({ visible: true }).first()
    const payCount = await payBtn.count()
    console.log('[report] botão de pagamento visível:', payCount)
    if (payCount) {
      await payBtn.click()
      await page.waitForTimeout(5000)
      const afterPay = await bodyText(page)
      console.log('[report] após pagar (300):', afterPay.slice(0, 300).replace(/\n/g, ' | '))
      await page.screenshot({ path: `artifacts/happy-paid-${ref}.png`, fullPage: true })
    }

    // 7) sem erros de console ao longo do fluxo
    const consoleErrors = realErrors(errors)
    console.log('[report] console errors:', consoleErrors.length ? consoleErrors.join(' || ') : '(nenhum)')
    expect(consoleErrors).toEqual([])

    test.info().annotations.push({ type: 'order-ref', description: ref })
  })
})
