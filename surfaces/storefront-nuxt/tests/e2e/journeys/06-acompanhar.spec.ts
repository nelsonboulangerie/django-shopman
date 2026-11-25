import { expect, test } from '@playwright/test'
import { auditStep } from './support/audit'
import { hydrated } from './support/experience'
import { addsFromMenu, goesToCheckout, opens, placesPickupTodayWithPix } from './support/steps'

// §5.1 · Acompanhar. Critério: poucos estágios em palavras simples, o detalhe embaixo. A
// cliente paga e volta ao pedido pela conta, como faria mais tarde.
const PRODUCT = 'Croissant'

test('acompanhar: o pedido pago, aberto pela conta', async ({ page }, testInfo) => {
  await opens(page)
  const ref = await test.step('um pedido de retirada hoje, pago com Pix', async () => {
    await addsFromMenu(page, testInfo, PRODUCT)
    await goesToCheckout(page)
    const placed = await placesPickupTodayWithPix(page, testInfo, false)
    await page.getByRole('button', { name: 'Simular pagamento' }).click()
    await expect(page.getByText('Pagamento recebido').first()).toBeVisible({ timeout: 60_000 })
    return placed
  })
  await test.step('a conta', async () => {
    await page.goto('/conta')
    await hydrated(page)
    await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()
    await auditStep(page, testInfo, 'conta')
  })
  await test.step('o acompanhamento: estágios e histórico', async () => {
    await page.goto(`/pedido/${encodeURIComponent(ref)}`)
    await hydrated(page)
    await expect(page.getByText('Pagamento recebido').first()).toBeVisible()
    await auditStep(page, testInfo, 'acompanhamento')
    const history = page.getByRole('tab', { name: 'Histórico' })
    if (await history.isVisible().catch(() => false)) {
      await history.click()
      await expect(page.getByRole('tabpanel', { name: 'Histórico' })).toBeVisible()
      await auditStep(page, testInfo, 'historico')
    }
  })
})
