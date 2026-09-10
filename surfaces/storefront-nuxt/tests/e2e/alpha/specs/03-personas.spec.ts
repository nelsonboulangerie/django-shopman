import { test, expect } from '@playwright/test'
import { login, addToCart, goToCheckout, continueBtn, ensureContactSaved, realErrors, collectConsoleErrors, bodyText, TEST_NAME } from '../helpers'

// 03 — Personas: convidado (sem login) e cliente recorrente (conta + histórico + entrega).
test.describe('personas', () => {
  test('convidado: /finalizar exige login e redireciona preservando o next', async ({ page }) => {
    const errors = collectConsoleErrors(page)
    await page.goto('/finalizar', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    expect(page.url()).toContain('/entrar?next=/finalizar')
    await expect(page.locator('h1')).toHaveText(/Vamos entrar|Entrar/)
    expect(errors).toEqual([])
  })

  test('convidado: tela de conta exige login', async ({ page }) => {
    await page.goto('/conta', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2200)
    expect(page.url()).toContain('/entrar')
  })

  test('cliente recorrente: login e conta com dados do pedido anterior', async ({ page }) => {
    test.setTimeout(240_000)
    const errors = collectConsoleErrors(page)
    // instrumenta hydration mismatch com a URL em que ocorreu
    page.on('console', m => {
      if (/hydrat/i.test(m.text())) console.log(`[report] HYDRATION em ${new URL(page.url()).pathname}: ${m.text().slice(0, 120)}`)
    })
    await login(page)
    // perfil
    await page.goto('/conta', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    const perfil = await bodyText(page)
    console.log('[report] conta body (300):', perfil.slice(0, 300).replace(/\n/g, ' | '))
    // pedidos
    await page.goto('/conta/pedidos', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    const pedidos = await bodyText(page)
    console.log('[report] pedidos body (500):', pedidos.slice(0, 500).replace(/\n/g, ' | '))
    expect(pedidos.length).toBeGreaterThan(100)
    // navegação secundária da conta
    for (const sub of ['/conta/favoritos', '/conta/enderecos', '/conta/preferencias', '/conta/seguranca', '/conta/perfil']) {
      const r = await page.goto(sub, { waitUntil: 'domcontentloaded' })
      await page.waitForTimeout(1200)
      expect(r?.status(), `rota ${sub} deveria responder 200`).toBe(200)
      expect((await bodyText(page)).length).toBeGreaterThan(60)
    }
    expect(realErrors(errors)).toEqual([])
  })

  test('persona entrega: checkout com endereço novo (CEP da região)', async ({ page }) => {
    test.setTimeout(240_000)
    const errors = collectConsoleErrors(page)
    await login(page)
    // total ≥ mínimo de entrega (R$ 25,00)
    await addToCart(page, 'Croissant')
    await addToCart(page, 'Café Coado')
    await goToCheckout(page)

    // contato (pode vir pré-salvo do perfil)
    await ensureContactSaved(page)

    // Entrega
    const body2 = await bodyText(page)
    expect(body2).toMatch(/Retirada|Entrega/)
    const entrega = page.getByRole('radio', { name: /Entrega/i }).first()
    await expect(entrega).toBeVisible()
    await entrega.click()
    await page.waitForTimeout(1200)
    // confirma o fulfillment → ativa o passo Endereço
    const cont = continueBtn(page)
    await expect(cont).toBeVisible({ timeout: 10_000 })
    await cont.click()
    await page.waitForTimeout(3500)
    await page.screenshot({ path: 'artifacts/persona-entrega-address.png', fullPage: true })
    const bodyAddr = await bodyText(page)
    console.log('[report] passo endereço (500):', bodyAddr.slice(0, 500).replace(/\n/g, ' | '))

    // busca por CEP no AddressPicker (passo ativo)
    const cepInput = page.locator('input[placeholder*="CEP"], input[placeholder*="Rua, número"]').filter({ visible: true }).first()
    console.log('[report] cepInput count:', await cepInput.count())
    if (await cepInput.count()) {
      await cepInput.fill('86050-270')
      await page.waitForTimeout(3500)
      await page.screenshot({ path: 'artifacts/persona-entrega-suggestions.png', fullPage: true })
      const bodySug = await bodyText(page)
      console.log('[report] sugestões (300):', bodySug.slice(0, 300).replace(/\n/g, ' | '))
      const sug = page.locator('button, [role="option"], li').filter({ hasText: /Madre Leônia|Bela Suíça|86050/ }).filter({ visible: true }).first()
      console.log('[report] sugestão endereço count:', await sug.count())
      if (await sug.count()) {
        await sug.click()
        await page.waitForTimeout(2000)
        await page.screenshot({ path: 'artifacts/persona-entrega-selected.png', fullPage: true })
      }
    }
    // preenche Número (obrigatório) e confirma o endereço novo ("Usar este endereço")
    const numInput = page.locator('#address-number').filter({ visible: true }).first()
    if (await numInput.count()) {
      await numInput.fill('446')
      console.log('[report] número do endereço preenchido: 446')
      await page.waitForTimeout(1200)
      const usar = page.locator('[data-address-confirm]').filter({ visible: true }).first()
      console.log('[report] botão confirmar endereço count:', await usar.count())
      if (await usar.count()) {
        await usar.click()
        await page.waitForTimeout(3000)
      }
    }
    // sheet de etiqueta do endereço novo ("Como você quer chamar este endereço?")
    const etiqueta = page.getByText(/Como você quer chamar este endereço/i).first()
    if (await etiqueta.count()) {
      const casa = page.getByRole('button', { name: /^Casa$/i }).filter({ visible: true }).first()
      if (await casa.count()) { await casa.click(); await page.waitForTimeout(2500); console.log('[report] etiqueta do endereço: Casa') }
    }
    // passo Quando: seleciona data (Amanhã) e, se houver, primeiro horário disponível
    const amanha = page.getByRole('radio', { name: /Amanhã/i }).first()
    if (await amanha.count()) { await amanha.click(); await page.waitForTimeout(1000) }
    const slot = page.getByRole('radio', { name: /às|:00|h/i }).filter({ visible: true }).first()
    const slotCount = await slot.count()
    console.log('[report] slots de horário:', slotCount)
    if (slotCount) { await slot.click(); await page.waitForTimeout(800) }
    // avança: quando → pagamento → revisão → enviar
    for (let i = 0; i < 5; i++) {
      // CTA do passo ativo: "Continuar" (quando) ou "Revisar pedido" (pagamento)
      const c = continueBtn(page)
      const revisar = page.getByRole('button', { name: /Revisar pedido/i }).filter({ visible: true }).first()
      const cta = (await c.count()) ? c : ((await revisar.count()) ? revisar : null)
      if (!cta) break
      await cta.click()
      await page.waitForTimeout(2500)
      // sheet de revisão → confirma
      const sheet = page.getByRole('dialog').filter({ hasText: /Revise seu pedido/i }).first()
      if (await sheet.count()) {
        await page.screenshot({ path: 'artifacts/persona-entrega-sheet.png', fullPage: true })
        const sheetText = await sheet.innerText()
        console.log('[report] sheet entrega (300):', sheetText.slice(0, 300).replace(/\n/g, ' | '))
        const confirmar = sheet.getByRole('button').filter({ hasText: /Enviar|Confirmar/i }).last()
        if (await confirmar.count()) {
          await confirmar.click()
          await page.waitForTimeout(8000)
          break
        }
      }
    }
    const bodyFim = await bodyText(page)
    console.log('[report] final persona entrega URL:', page.url())
    console.log('[report] final persona entrega (400):', bodyFim.slice(0, 400).replace(/\n/g, ' | '))
    const ref = page.url().match(/\/pedido\/([^/]+)/)
    if (ref) console.log('[report] DELIVERY_ORDER_REF=' + ref[1])
    expect(bodyFim.length).toBeGreaterThan(100)
    expect(realErrors(errors)).toEqual([])
  })
})
