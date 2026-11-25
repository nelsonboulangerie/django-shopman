import { expect, test } from '@playwright/test'
import { auditStep } from './support/audit'
import { addsFromMenu, goesToCheckout, opens, placesPickupTodayWithPix } from './support/steps'

// §5.1 · Pagamento Pix. Critério: código visível, botão de copiar com retorno anunciado,
// prazo de validade em texto, estado atualizado sozinho (SSE) depois de pagar. O pedido
// sai sem auditar o checkout (a jornada "pedir hoje" já mede essas telas).
const PRODUCT = 'Croissant'

test('Pix: o código, o copiar, o prazo e o pagamento que chega sozinho', async ({ page }, testInfo) => {
  await opens(page)
  await test.step('um pedido de retirada hoje com Pix', async () => {
    await addsFromMenu(page, testInfo, PRODUCT)
    await goesToCheckout(page)
    await placesPickupTodayWithPix(page, testInfo, false)
  })
  await test.step('o Pix à espera: código, copiar e prazo', async () => {
    const copy = page.getByRole('button', { name: /Copiar/ }).first()
    await expect(copy).toBeVisible()
    await auditStep(page, testInfo, 'pix-a-pagar')
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
    await copy.click()
    await auditStep(page, testInfo, 'pix-copiado', { widths: ['375'] })
  })
  await test.step('pago: a tela muda sem recarregar', async () => {
    await page.getByRole('button', { name: 'Simular pagamento' }).click()
    await expect(page.getByText('Pagamento recebido').first()).toBeVisible({ timeout: 60_000 })
    await auditStep(page, testInfo, 'pix-pago')
  })
})
