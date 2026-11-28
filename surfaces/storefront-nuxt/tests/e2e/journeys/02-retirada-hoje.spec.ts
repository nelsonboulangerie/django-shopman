import { expect, test } from '@playwright/test'
import { auditStep } from './support/audit'
import { addsFromMenu, goesToCheckout, opens, placesPickupTodayWithPix } from './support/steps'

// §5.1 · Pedir hoje (retirada). Critério: produto → sacola → horário → pagamento →
// acompanhamento sem ajuda, a 375 px e com a fonte ampliada (X11 em cada passo).
const PRODUCT = 'Croissant' // pronto agora no seed `--profile qa`

test('pedir hoje: retirada com Pix, do cardápio ao acompanhamento', async ({ page }, testInfo) => {
  await opens(page)
  await test.step('cardápio, produto e sacola', async () => {
    await addsFromMenu(page, testInfo, PRODUCT)
  })
  await test.step('finalizar: retirada, hoje, horário, Pix, revisar e enviar', async () => {
    await goesToCheckout(page)
    await placesPickupTodayWithPix(page, testInfo)
  })
  await test.step('o acompanhamento do pedido enviado', async () => {
    await expect(page.getByRole('button', { name: 'Simular pagamento' })).toBeVisible()
    await auditStep(page, testInfo, 'acompanhamento')
  })
})
