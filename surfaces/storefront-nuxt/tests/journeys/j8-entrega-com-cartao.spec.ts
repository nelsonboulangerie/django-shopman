import { expect, test, type APIRequestContext, type Locator, type Page } from '@playwright/test'
import { addReadyProductFromMenu, checkoutSigningInByCode } from './support/customer'
import { acceptsNewOrder, acknowledgeOtherOrdersAlarms, managerSignsIn } from './support/operator'
import { viaCepFromFakeMaps } from './support/maps'
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
// endereço entra pelo caminho manual do AddressPicker (a pilha não tem Google). O ViaCEP que
// o navegador consulta ao digitar o CEP vai aos mapas falsos da pilha, e nenhuma consulta
// sai da máquina (#3282). O aviso do pedido chega no WhatsApp dela: o ManyChat falso da
// pilha o guarda, e a jornada o lê pelo telefone.
const PRODUCT = 'Croissant'
const ADDRESS = { route: 'Rua Jorge Velho', number: '140', neighborhood: 'Bela Suíça', cep: '86050-480' }

// O ManyChat falso da pilha (shopman/shop/tests/e2e/fake_manychat.py).
const MANYCHAT = (process.env.JOURNEY_MANYCHAT_URL || `http://127.0.0.1:${process.env.JOURNEYS_MANYCHAT_PORT || '12191'}`).replace(/\/$/, '')

/** As mensagens que a loja mandou ao WhatsApp deste telefone, como o ManyChat falso guardou. */
async function whatsappMessages (request: APIRequestContext, phone: string): Promise<{ endpoint: string }[]> {
  const response = await request.get(`${MANYCHAT}/__sent?phone=55${phone}`)
  expect(response.status()).toBe(200)
  const { sent } = await response.json() as { sent: { endpoint: string }[] }
  return sent.filter(item => item.endpoint.startsWith('/fb/sending/'))
}

/** O passo "Endereço" pelo caminho manual, como a cliente que digita o endereço: o CEP
 *  primeiro (o formulário abre nele), que preenche rua, bairro, cidade e UF pelo ViaCEP (aqui,
 *  os mapas falsos); ela completa o número e confirma. */
async function typesDeliveryAddress (page: Page) {
  const step = page.locator("[data-checkout-step='address']")
  await expect(step.locator('[data-address-picker]')).toBeVisible()
  const fresh = step.locator('[data-address-new]')
  if (await fresh.first().isVisible().catch(() => false)) await tapsWithKeyboardClosed(page, fresh.first())
  await tapsWithKeyboardClosed(page, step.locator('[data-address-manual]'))
  await step.locator('#address-cep').pressSequentially(ADDRESS.cep.replace('-', ''))
  // A consulta do CEP preencheu o resto: a rua, o bairro e a cidade dele.
  await expect(step.locator('#address-route')).toHaveValue(ADDRESS.route)
  await expect(step.locator('#address-neighborhood')).toHaveValue(ADDRESS.neighborhood)
  await expect(step.locator('#address-city')).toHaveValue('Londrina')
  await step.locator('#address-number').fill(ADDRESS.number)
  await tapsWithKeyboardClosed(page, step.locator('[data-address-confirm]'))
}

/** Fecha o teclado e toca no botão. Na emulação de celular não há teclado de verdade
 *  ocupando a base da tela: com um campo em foco a loja recolhe a barra de baixo e o card de
 *  ação, o botão pode ficar na borda inferior, e o clique (o mousedown tira o foco, a barra
 *  volta por cima do botão, o mouseup cai nela) se perde. Medido na J8 a 375 px: depois do
 *  clique, o ponto do botão era o link "Sacola" da barra. No aparelho, o teclado ocupa esse
 *  lugar e a barra volta onde ele estava. */
async function tapsWithKeyboardClosed (page: Page, button: Locator) {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
  await button.click()
}

/** "Quando" da entrega: a primeira janela habilitada da data marcada. */
async function picksFirstDeliveryWindow (page: Page) {
  const when = page.locator("[data-checkout-step='when']")
  const window = when.locator("[data-checkout-delivery-windows] [role='radio']:not([data-disabled]):not([disabled])").first()
  await expect(window).toBeVisible({ timeout: 30_000 })
  await window.click()
  await expect(window).toHaveAttribute('aria-checked', 'true')
}

test('J8: entrega com cartão, passando pelo mínimo da entrega, até a loja aceitar', async ({ page, browser, request }, testInfo) => {
  test.setTimeout(300_000)
  const customer = { phone: newCustomerPhone(), name: 'Rosa' }
  const viaCep = await viaCepFromFakeMaps(page)

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
    // O dinheiro, na mesma aba: o cartão pago, com o valor, depois da captura no aceite.
    await expect(page.getByRole('tabpanel', { name: 'Resumo' })).toContainText(/Cartão de R\$\s*\d+,\d{2}, pago às \d{1,2}h\d{2}/)
    await capture(page, testInfo, 'entrega')
  })

  await test.step('o CEP foi consultado nos mapas falsos, e nada saiu para o ViaCEP de verdade', async () => {
    expect(viaCep.served).toContain(ADDRESS.cep.replace('-', ''))
    expect(viaCep.refused).toEqual([])
  })

  await test.step('o aviso do pedido chega no WhatsApp dela', async () => {
    // Ela entrou por código: o contato do ManyChat nasce do telefone, pelo resolvedor.
    await expect.poll(async () => (await whatsappMessages(request, customer.phone)).length, {
      message: 'o ManyChat falso recebeu o aviso do pedido para o telefone dela',
      timeout: 60_000
    }).toBeGreaterThan(0)
  })
})
