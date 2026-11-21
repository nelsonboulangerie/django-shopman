import { expect, test } from '@playwright/test'
import { addReadyProductFromMenu, checkoutSigningInByCode, placePickupTodayWithPix } from './support/customer'
import { capture, newCustomerPhone, settled } from './support/stack'

// J7 · Repetir o pedido (docs/plans/EXCELENCIA-STOREFRONT-PLANO.md, seção 8; #2681).
//
// Papel: a cliente que volta. Ela faz um pedido (retirada hoje, Pix), desiste dele no
// acompanhamento e, ali mesmo, pede de novo: "Repetir pedido" leva os mesmos itens à sacola,
// e o checkout já sabe quem ela é e o que ela escolheu da outra vez.
//
// O caminho até "Repetir pedido" é o da própria cliente. O botão só aparece com o pedido
// encerrado (concluído, cancelado ou devolvido), e cancelar o próprio pedido ainda não pago
// é um gesto dela. Nenhum estado nasce por API, Admin ou banco.
const PRODUCT = 'Croissant' // pronto agora no seed `--profile qa`

test('J7: a cliente desiste do pedido e o repete do acompanhamento, com as escolhas lembradas', async ({ page }, testInfo) => {
  const customer = { phone: newCustomerPhone(), name: 'Teresa' }

  await test.step('a cliente faz o primeiro pedido: retirada hoje, Pix', async () => {
    await addReadyProductFromMenu(page, testInfo, PRODUCT)
    await checkoutSigningInByCode(page, testInfo, customer)
    await placePickupTodayWithPix(page, testInfo)
  })

  await test.step('desiste dele no acompanhamento', async () => {
    await page.getByRole('button', { name: 'Cancelar pedido' }).first().click()
    const dialog = page.getByRole('alertdialog')
    await expect(dialog).toBeVisible()
    await capture(page, testInfo, 'cancelar-confirma')
    // O segundo botão do diálogo é a confirmação; o primeiro volta sem cancelar.
    await dialog.getByRole('button').nth(1).click()
    await expect(dialog).toBeHidden()
    await expect(page.getByRole('button', { name: 'Repetir pedido' }).first()).toBeVisible({ timeout: 30_000 })
    await capture(page, testInfo, 'cancelado-com-repetir')
  })

  await test.step('"Repetir pedido" leva os mesmos itens à sacola', async () => {
    await page.getByRole('button', { name: 'Repetir pedido' }).first().click()
    await expect(page).toHaveURL(/\/sacola$/)
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Sua sacola' })).toBeVisible()
    await expect(page.getByRole('group', { name: `Quantidade de ${PRODUCT}` }).first()).toContainText('1')
    await capture(page, testInfo, 'sacola-repetida')
  })

  await test.step('o checkout já sabe quem ela é e o que escolheu da outra vez', async () => {
    await page.getByRole('link', { name: 'Finalizar pedido' }).last().click()
    // Já entrou: o checkout abre direto, sem pedir o código de novo.
    await expect(page).toHaveURL(/\/finalizar/)
    await settled(page)
    // O contato já vem feito, com quem ela é (nome e telefone na mesma linha).
    await expect(page.getByText(new RegExp(`^${customer.name} \\(\\d{2}\\) \\d{4,5}-\\d{4}$`)).first()).toBeVisible()
    // As escolhas da outra vez voltam: retirada, hoje, Pix.
    await expect(page.getByRole('radio', { name: /^Retirada/ })).toBeChecked()
    await expect(page.getByText(/^Hoje · \d{1,2}h(\d{2})? às \d{1,2}h(\d{2})?$/).first()).toBeVisible()
    await expect(page.locator('[data-checkout-step="payment"]').getByText('Pix', { exact: true }).first()).toBeVisible()
    await capture(page, testInfo, 'checkout-lembrado')
  })
})
