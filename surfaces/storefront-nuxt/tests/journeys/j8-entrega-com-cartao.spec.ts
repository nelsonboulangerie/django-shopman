import { expect, test, type Page } from '@playwright/test'
import { addReadyProductFromMenu, checkoutSigningInByCode } from './support/customer'
import { acceptsNewOrder, acknowledgeOtherOrdersAlarms, managerSignsIn } from './support/operator'
import { capture, gestorViewport, newCustomerPhone, settled, stack } from './support/stack'

// J8 · Entrega com cartão (docs/plans/EXCELENCIA-STOREFRONT-PLANO.md, seção 8; #2987).
//
// Papéis: a cliente que volta e a operadora no Gestor. Os passos do plano: entrega,
// abaixo do mínimo, trocar por retirada, voltar à entrega com o mínimo, cartão em um
// toque. Depois, a loja aceita (o aceite CAPTURA a cobrança no cartão) e o acompanhamento
// diz do pedido e da entrega.
//
// O seed `--profile qa` cobra R$ 25,00 de mínimo só na entrega; um Croissant (R$ 13,00)
// fica abaixo, dois passam. O cartão vai ao Stripe falso da pilha (F-7, #2568), e o
// endereço entra pelo caminho manual do AddressPicker (a pilha não tem Google).
const PRODUCT = 'Croissant'
const ADDRESS = { route: 'Rua Jorge Velho', number: '140', neighborhood: 'Bela Suíça', cep: '86050-480' }

/** O passo "Endereço" pelo caminho manual, como a cliente que digita o endereço. */
async function typesDeliveryAddress (page: Page) {
  const step = page.locator("[data-checkout-step='address']")
  await expect(step.locator('[data-address-picker]')).toBeVisible()
  const fresh = step.locator('[data-address-new]')
  if (await fresh.first().isVisible().catch(() => false)) await fresh.first().click()
  await step.locator('[data-address-manual]').click()
  await step.locator('#address-route').fill(ADDRESS.route)
  await step.locator('#address-number').fill(ADDRESS.number)
  await step.locator('#address-neighborhood').fill(ADDRESS.neighborhood)
  await step.locator('#address-cep').fill(ADDRESS.cep)
  const city = step.locator('#address-city')
  if (!(await city.inputValue()).trim()) await city.fill('Londrina')
  const state = step.locator('#address-state')
  if (!(await state.innerText()).trim()) {
    await state.click()
    await page.getByRole('option', { name: 'PR', exact: true }).click()
  }
  await step.locator('[data-address-confirm]').click()
}

/** "Quando" da entrega: a primeira janela habilitada da data marcada. */
async function picksFirstDeliveryWindow (page: Page) {
  const when = page.locator("[data-checkout-step='when']")
  const window = when.locator("[data-checkout-delivery-windows] [role='radio']:not([data-disabled]):not([disabled])").first()
  await expect(window).toBeVisible({ timeout: 30_000 })
  await window.click()
  await expect(window).toHaveAttribute('aria-checked', 'true')
}

test('J8: entrega com cartão, passando pelo mínimo da entrega, até a loja aceitar', async ({ page, browser }, testInfo) => {
  test.setTimeout(300_000)
  const customer = { phone: newCustomerPhone(), name: 'Rosa' }

  const gestorContext = await browser.newContext({ baseURL: stack.gestor, viewport: gestorViewport, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' })
  const gestor = await gestorContext.newPage()
  try {
    await test.step('a operadora abre o Gestor', async () => {
      await acknowledgeOtherOrdersAlarms(gestor)
      await managerSignsIn(gestor)
    })

    await test.step('um Croissant na sacola: abaixo do mínimo da entrega', async () => {
      await addReadyProductFromMenu(page, testInfo, PRODUCT)
      await checkoutSigningInByCode(page, testInfo, customer)
      await page.getByRole('radio', { name: /^Entrega/ }).click()
      const minimum = page.locator('[data-checkout-delivery-minimum]')
      await expect(minimum).toContainText(/Faltam R\$\s*\d+,\d{2} para o mínimo de entrega/)
      await capture(page, testInfo, 'abaixo-do-minimo')
    })

    await test.step('troca por retirada, que não tem mínimo', async () => {
      await page.getByRole('button', { name: 'Prefere retirar? Sem mínimo.' }).click()
      await expect(page.getByRole('radio', { name: /^Retirada/ })).toBeChecked()
      await expect(page.locator('[data-checkout-delivery-minimum]')).toHaveCount(0)
    })

    await test.step('volta à entrega com o mínimo: mais um Croissant', async () => {
      await page.getByRole('radio', { name: /^Entrega/ }).click()
      await page.locator('[data-checkout-minimum-add-items]').click()
      await page.waitForURL(/\/(menu|produto)/)
      await settled(page)
      await page.goto('/sacola')
      await settled(page)
      await page.getByRole('group', { name: `Quantidade de ${PRODUCT}` }).getByRole('button', { name: /Adicionar|Aumentar|Mais/i }).first().click()
      await expect(page.getByRole('group', { name: `Quantidade de ${PRODUCT}` })).toContainText('2')
      await page.getByRole('link', { name: 'Finalizar pedido' }).last().click()
      await expect(page).toHaveURL(/\/finalizar/)
      await settled(page)
      await page.getByRole('radio', { name: /^Entrega/ }).click()
      await expect(page.locator('[data-checkout-delivery-minimum]')).toHaveCount(0)
      await capture(page, testInfo, 'minimo-atingido')
    })

    const ref = await test.step('endereço, janela, cartão em um toque, e paga', async () => {
      await typesDeliveryAddress(page)
      await picksFirstDeliveryWindow(page)
      await page.getByRole('button', { name: 'Continuar', exact: true }).click()
      await page.getByRole('radio', { name: /^Cartão/ }).click()
      await page.getByRole('button', { name: 'Revisar pedido' }).click()
      await expect(page.getByRole('heading', { name: 'Revise seu pedido' })).toBeVisible()
      await capture(page, testInfo, 'revisar-entrega-cartao')
      const visited: string[] = []
      page.on('framenavigated', frame => { if (frame === page.mainFrame()) visited.push(frame.url()) })
      // Cartão em um toque: depois de enviar, a loja leva sozinha ao pagamento seguro.
      await page.getByRole('button', { name: 'Enviar pedido' }).click()
      await page.waitForURL(/\/pay\/cs_test_/, { timeout: 60_000 })
      const ref = visited.map(url => url.match(/\/pedido\/([^/?#]+)/)?.[1]).find(Boolean)
      expect(ref, 'a loja deveria passar pelo acompanhamento antes do pagamento').toBeTruthy()
      await page.getByRole('button', { name: 'Pagar' }).click()
      await page.waitForURL(new RegExp(`/pedido/${ref}(\\?.*)?$`), { timeout: 60_000 })
      await settled(page)
      await expect(page.getByText('Pagamento autorizado').first()).toBeVisible({ timeout: 30_000 })
      await capture(page, testInfo, 'cartao-autorizado')
      return decodeURIComponent(ref!)
    })

    await test.step('a operadora aceita: o aceite captura o cartão', async () => {
      await acceptsNewOrder(gestor, testInfo, ref)
    })
  } finally {
    await gestorContext.close()
  }

  await test.step('o acompanhamento diz do pedido aceito e da entrega', async () => {
    await expect(page.getByRole('tabpanel', { name: 'Histórico' }).getByText(/^Aceito/).first()).toBeVisible({ timeout: 60_000 })
    await capture(page, testInfo, 'aceito')
    // O endereço da entrega mora na aba "Resumo" do acompanhamento.
    await page.getByRole('tab', { name: 'Resumo', exact: true }).click()
    await expect(page.getByRole('tabpanel', { name: 'Resumo' })).toContainText(new RegExp(`${ADDRESS.route},?\\s*${ADDRESS.number}`))
    await capture(page, testInfo, 'entrega')
  })
})
