import { expect, test } from '@playwright/test'
import { addReadyProductFromMenu, checkoutSigningInByCode, placePickupTodayPayingByCard } from './support/customer'
import { acceptsNewOrder, acknowledgeOtherOrdersAlarms, managerSignsIn } from './support/operator'
import { capture, gestorViewport, newCustomerPhone, settled, stack } from './support/stack'

// J13 · Cancelar depois do preparo (#2569, item 2): o caminho "falar com o responsável".
//
// Papéis: a cliente que paga com cartão e a operadora no Gestor. A régua do dono (06/11):
// antes do preparo a cliente cancela sozinha (J6); depois que o preparo começou o pedido é
// feito para ela e não se cancela mais. No lugar do "Cancelar pedido", o acompanhamento
// oferece falar com o responsável, e o Gestor abre a ouvidoria no pedido até alguém
// marcar Resolvido com o que foi feito.
//
// Na loja online o preparo NÃO começa sozinho no aceite (`prep_start="operator"`,
// `_prep_starts_automatically` em shopman/shop/lifecycle.py): o Cappuccino, feito na hora,
// ganha ticket na estação Cafés, e o pedido fica Aceito até o "Iniciar preparo". A
// operadora dá o atalho do Gestor, que é o mesmo ato da Cozinha.
const PRODUCT = 'Cappuccino'

test('J13: depois do preparo, a cliente fala com o responsável no lugar de cancelar', async ({ page, browser }, testInfo) => {
  test.setTimeout(300_000)
  const customer = { phone: newCustomerPhone(), name: 'Helena' }

  const gestorContext = await browser.newContext({ baseURL: stack.gestor, viewport: gestorViewport, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' })
  const gestor = await gestorContext.newPage()
  try {
    await test.step('a operadora abre o Gestor', async () => {
      await acknowledgeOtherOrdersAlarms(gestor)
      await managerSignsIn(gestor)
    })

    const ref = await test.step('a cliente pede um Cappuccino e paga com cartão', async () => {
      await addReadyProductFromMenu(page, testInfo, PRODUCT)
      await checkoutSigningInByCode(page, testInfo, customer)
      return await placePickupTodayPayingByCard(page, testInfo)
    })

    await test.step('a operadora aceita e inicia o preparo', async () => {
      await acceptsNewOrder(gestor, testInfo, ref)
      await gestor.goto(`/${encodeURIComponent(ref)}`)
      await settled(gestor)
      await gestor.getByRole('button', { name: 'Iniciar preparo', exact: true }).first().click()
      await expect(gestor.getByRole('button', { name: 'Iniciar preparo', exact: true })).toHaveCount(0, { timeout: 30_000 })
      await capture(gestor, testInfo, 'gestor-em-preparo')
    })

    await test.step('no acompanhamento, o cancelar some e entra o falar com o responsável', async () => {
      const contact = page.locator('[data-cancellation-contact]')
      await expect(contact).toBeVisible({ timeout: 60_000 })
      await expect(page.getByRole('button', { name: 'Cancelar pedido', exact: true })).toHaveCount(0)
      await expect(contact).toContainText('Quer cancelar?')
      await expect(contact).toContainText('O preparo já começou e o pedido é feito para você')
      await contact.scrollIntoViewIfNeeded()
      await capture(page, testInfo, 'quer-cancelar')

      await contact.getByRole('button').click()
      await expect(contact).toContainText('Contato solicitado')
      await expect(contact.getByRole('status')).toContainText('O responsável pela casa vai te chamar no WhatsApp.')
      await expect(contact.getByRole('button')).toHaveCount(0)
      await capture(page, testInfo, 'contato-solicitado')
    })

    await test.step('o Gestor abre a ouvidoria no pedido', async () => {
      await acknowledgeOtherOrdersAlarms(gestor, ref)
      await gestor.goto(`/${encodeURIComponent(ref)}`)
      await settled(gestor)
      const notice = gestor.locator('[data-contact-request]')
      await expect(notice).toBeVisible({ timeout: 60_000 })
      await expect(notice).toContainText('Ouvidoria aberta: o cliente queria cancelar')
      await expect(notice).toContainText('O pedido segue; chame o cliente e marque Resolvido com o que foi combinado.')
      await capture(gestor, testInfo, 'gestor-ouvidoria')
    })

    await test.step('a operadora conversa e marca Resolvido com o que foi feito', async () => {
      await gestor.locator('[data-contact-request]').getByRole('button', { name: 'Resolvido', exact: true }).click()
      const dialog = gestor.getByRole('dialog').filter({ has: gestor.getByRole('heading', { name: 'Ouvidoria resolvida' }) })
      await expect(dialog).toBeVisible()
      const reason = dialog.getByRole('textbox', { name: 'O que foi feito' })
      await reason.click()
      await reason.pressSequentially('Falei com a cliente no WhatsApp; ela fica com o pedido.')
      await capture(gestor, testInfo, 'gestor-resolver')
      await dialog.getByRole('button', { name: 'Marcar resolvido', exact: true }).click()
      await expect(dialog).toBeHidden()
      await expect(gestor.locator('[data-contact-request]')).toHaveCount(0, { timeout: 30_000 })
      await capture(gestor, testInfo, 'gestor-resolvido')
    })
  } finally {
    await gestorContext.close()
  }

  await test.step('o acompanhamento continua dizendo que o contato foi pedido', async () => {
    await page.reload()
    await settled(page)
    const contact = page.locator('[data-cancellation-contact]')
    await expect(contact).toContainText('Contato solicitado')
    await expect(page.getByRole('button', { name: 'Cancelar pedido', exact: true })).toHaveCount(0)
    await capture(page, testInfo, 'acompanhamento-depois')
  })
})
