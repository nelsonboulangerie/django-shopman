import { expect, test } from '@playwright/test'
import { addReadyProductFromMenu, checkoutSigningInByCode, paysPixOnTracking, placePickupTodayWithPix } from './support/customer'
import { acceptsNewOrder, acknowledgeOtherOrdersAlarms, managerSignsIn } from './support/operator'
import { capture, gestorViewport, newCustomerPhone, stack } from './support/stack'

// J1 · Retirada para hoje com Pix (docs/plans/EXCELENCIA-STOREFRONT-PLANO.md, seção 8).
//
// Papéis: a cliente nova (na largura do projeto: 375 ou 1366 px) e a operadora (Gerente,
// no Gestor, 1366 px). A cliente abre o cardápio, põe um item pronto na sacola, entra pelo
// código que chegou, escolhe retirada para hoje, paga o Pix simulado e fica olhando o
// acompanhamento. A operadora aceita no Gestor. A tela da cliente muda sozinha: a página
// do acompanhamento não é recarregada, e a suíte prova isso com uma marca na janela.
//
// A ordem importa: o Gestor fica aberto ANTES de a cliente pedir. Pedido pago tem poucos
// minutos para ser aceito antes de cancelar sozinho, e ninguém abre o balcão com o relógio
// correndo.
const PRODUCT = 'Croissant' // pronto agora no seed `--profile qa` (vitrine do perfil)

test('J1: a cliente nova pede retirada para hoje com Pix e vê a loja aceitar', async ({ page, browser }, testInfo) => {
  const customer = { phone: newCustomerPhone(), name: 'Teresa' }

  const gestorContext = await browser.newContext({ baseURL: stack.gestor, viewport: gestorViewport, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' })
  const gestor = await gestorContext.newPage()
  try {
    await test.step('a operadora abre o Gestor', async () => {
      await acknowledgeOtherOrdersAlarms(gestor)
      await managerSignsIn(gestor)
      await capture(gestor, testInfo, 'gestor-aberto')
    })

    await test.step('a cliente põe um item pronto na sacola', async () => {
      await addReadyProductFromMenu(page, testInfo, PRODUCT)
    })

    await test.step('a cliente entra pelo código que chegou', async () => {
      await checkoutSigningInByCode(page, testInfo, customer)
    })

    const ref = await test.step('a cliente pede retirada para hoje com Pix', async () => {
      return await placePickupTodayWithPix(page, testInfo)
    })

    await test.step('a cliente paga o Pix e fica no acompanhamento', async () => {
      await paysPixOnTracking(page, testInfo)
    })

    // Daqui em diante a página da cliente não é tocada: o que mudar nela chegou sozinho.
    await page.evaluate(() => { (window as Window & { __j1SameVisit?: boolean }).__j1SameVisit = true })

    await test.step('a operadora aceita o pedido no Gestor', async () => {
      await acceptsNewOrder(gestor, testInfo, ref)
    })
  } finally {
    await gestorContext.close()
  }

  await test.step('o acompanhamento da cliente muda sozinho', async () => {
    // O título do aviso segue "Pagamento recebido" (o pagamento é o fato da cliente); a
    // frase troca de "conferindo" para "aceito" e o histórico ganha o passo "Aceito".
    await expect(page.getByText('Pedido aceito. Acompanhe o andamento por aqui.').first()).toBeVisible({ timeout: 60_000 })
    await expect(page.getByText(/A loja confirma a disponibilidade/)).toHaveCount(0)
    // O passo do histórico. O título do passo está fora da árvore de acessibilidade
    // (aria-hidden, #2609): até o #2609 fechar, a suíte o acha pelo slot do componente.
    await expect(page.getByRole('tabpanel', { name: 'Histórico' }).locator('[data-slot="timeline-title"]', { hasText: /^Aceito/ })).toBeVisible()
    expect(await page.evaluate(() => (window as Window & { __j1SameVisit?: boolean }).__j1SameVisit)).toBe(true)
    await capture(page, testInfo, 'aceito')
  })
})
