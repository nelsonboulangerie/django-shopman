import { expect, test, type Page } from '@playwright/test'
import { viaCepFromFakeMaps } from '../../journeys/support/maps'
import { auditStep } from './support/audit'
import { hydrated } from './support/experience'
import { addsFromMenu, goesToCheckout, opens } from './support/steps'

// §5.1 · Entrega. Critério: endereço fora da zona é dito ANTES do pagamento, com
// alternativa. O endereço vai pelo CEP; o ViaCEP e o geocoding são os mapas falsos da
// pilha (shopman/shop/tests/e2e/fake_maps.py), com o mesmo endereço da J15 (14,8 km).
const PRODUCT = 'Croissant'
const OUTSIDE = { cep: '86118-000', route: 'Estrada do Limoeiro', number: '10', neighborhood: 'Irerê' }

/** Abre o formulário de endereço novo (a cliente já tem um salvo) e digita pelo CEP. */
async function typesNewAddress (page: Page): Promise<void> {
  const step = page.locator("[data-checkout-step='address']")
  const editing = step.getByRole('button', { name: 'Editar', exact: true })
  if (await editing.isVisible().catch(() => false)) await editing.click()
  await expect(step.locator('[data-address-picker]')).toBeVisible()
  const form = step.locator('[data-address-form-card]')
  if (!(await form.isVisible().catch(() => false))) {
    const fresh = step.locator('[data-address-new]')
    if (await fresh.first().isVisible().catch(() => false)) await fresh.first().click()
    const manual = step.locator('[data-address-manual]')
    if (await manual.isVisible().catch(() => false)) await manual.click()
  }
  for (const field of ['#address-route', '#address-number', '#address-neighborhood']) await step.locator(field).fill('')
  const cep = step.locator('#address-cep')
  await cep.fill('')
  await cep.pressSequentially(OUTSIDE.cep.replace('-', ''))
  await expect(step.locator('#address-route')).toHaveValue(OUTSIDE.route)
  await step.locator('#address-number').fill(OUTSIDE.number)
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
  await step.locator('[data-address-confirm]').click()
}

test('entrega: o endereço fora da área é dito antes do pagamento, com a retirada como saída', async ({ page }, testInfo) => {
  await viaCepFromFakeMaps(page)
  await opens(page)
  await test.step('dois Croissants na sacola (o mínimo da entrega)', async () => {
    await addsFromMenu(page, testInfo, PRODUCT)
    const quantity = page.getByRole('group', { name: `Quantidade de ${PRODUCT}` }).first()
    await quantity.getByRole('button', { name: `Aumentar ${PRODUCT}` }).click()
    await expect(quantity).toContainText('2')
  })
  await test.step('finalizar com entrega', async () => {
    await goesToCheckout(page)
    await page.getByRole('radio', { name: /^Entrega/ }).click()
    await hydrated(page)
    await auditStep(page, testInfo, 'finalizar-entrega')
  })
  await test.step('um endereço a 14,8 km: a loja recusa e oferece a retirada', async () => {
    await typesNewAddress(page)
    const refusal = page.locator('[data-checkout-pickup-swap]')
    await expect(refusal).toBeVisible({ timeout: 30_000 })
    await expect(refusal).toContainText('Ainda não entregamos nesse endereço')
    // Antes do pagamento: o passo do pagamento ainda não abriu.
    await expect(page.getByRole('radio', { name: /^Pix/ })).toHaveCount(0)
    await auditStep(page, testInfo, 'fora-da-area')
  })
  await test.step('a troca para retirada leva o pedido adiante', async () => {
    await page.locator('[data-checkout-pickup-swap]').getByRole('button', { name: 'Mudar para retirada' }).click()
    await expect(page.getByRole('radio', { name: /^Retirada/ })).toBeChecked()
    await expect(page.getByText('Horário da retirada')).toBeVisible()
    await auditStep(page, testInfo, 'trocou-para-retirada')
  })
})
