import { expect, test } from '@playwright/test'
import { addReadyProductFromMenu, checkoutSigningInByCode, paysPixOnTracking, placePickupTodayWithPix } from './support/customer'
import { acknowledgeOtherOrdersAlarms, managerSignsIn, refusesOrder } from './support/operator'
import { capture, gestorViewport, newCustomerPhone, settled, stack } from './support/stack'

// J4 · Paguei e a loja não aceitou (docs/plans/EXCELENCIA-STOREFRONT-PLANO.md, seção 8; #2750).
//
// Papéis: a cliente (na largura do projeto) e a Gerente no Gestor (1366 px). A cliente paga
// o Pix e fica olhando o acompanhamento; a operadora recusa o pedido no Gestor. A tela da
// cliente muda sozinha (a página não é recarregada, e uma marca na janela prova isso) e diz
// o que aconteceu com o dinheiro; o estorno sai pelo worker da pilha, com o Pix simulado, e o
// histórico ganha "Devolvido".
const PRODUCT = 'Croissant' // pronto agora no seed `--profile qa`

type Marked = Window & { __j4SameVisit?: boolean }

test('J4: a cliente paga o Pix, a loja recusa no Gestor e o dinheiro volta', async ({ page, browser }, testInfo) => {
  test.setTimeout(300_000)
  const customer = { phone: newCustomerPhone(), name: 'Teresa' }

  const gestorContext = await browser.newContext({ baseURL: stack.gestor, viewport: gestorViewport, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' })
  const gestor = await gestorContext.newPage()
  try {
    await test.step('a operadora abre o Gestor', async () => {
      await acknowledgeOtherOrdersAlarms(gestor)
      await managerSignsIn(gestor)
    })

    const ref = await test.step('a cliente pede retirada para hoje e paga o Pix', async () => {
      await addReadyProductFromMenu(page, testInfo, PRODUCT)
      await checkoutSigningInByCode(page, testInfo, customer)
      const placed = await placePickupTodayWithPix(page, testInfo)
      await paysPixOnTracking(page, testInfo)
      return placed
    })

    // Daqui em diante a página da cliente não é tocada: o que mudar nela chegou sozinho.
    await page.evaluate(() => { (window as Marked).__j4SameVisit = true })

    await test.step('a operadora recusa o pedido no Gestor', async () => {
      await refusesOrder(gestor, testInfo, ref)
    })
  } finally {
    await gestorContext.close()
  }

  await test.step('o acompanhamento diz que a loja não aceitou e que o dinheiro volta', async () => {
    const history = page.getByRole('tabpanel', { name: 'Histórico' })
    await expect(history.getByText(/^Cancelado/).first()).toBeVisible({ timeout: 60_000 })
    await capture(page, testInfo, 'cliente-recusado')
    // O motivo da loja e o caminho do dinheiro, na frase principal.
    await expect(page.getByText(/Motivo do cancelamento: /).first()).toBeVisible()
    await expect(page.getByText(/Devolvemos os R\$ \d+,\d{2} do seu Pix para a mesma conta\./).first()).toBeVisible()
    // O estorno sai pelo worker (Pix simulado): o histórico ganha o marco do dinheiro.
    await expect(history.getByText(/^Devolvido · R\$ \d+,\d{2}/).first()).toBeVisible({ timeout: 120_000 })
    expect(await page.evaluate(() => (window as Marked).__j4SameVisit), 'a página da cliente foi recarregada').toBe(true)
    await capture(page, testInfo, 'cliente-devolvido')
  })

  await test.step('a conta lista o pedido cancelado', async () => {
    await page.goto('/conta/pedidos')
    await settled(page)
    // Hoje a lista diz "Cancelado · R$ 13,00" e não diz que o dinheiro voltou: o plano
    // pede "Devolvido" também na conta, e isso é tela (#2992).
    await expect(page.locator('main')).toContainText(/Cancelado\s*·\s*R\$\s*\d+,\d{2}/)
    await capture(page, testInfo, 'conta-pedidos')
  })
})
