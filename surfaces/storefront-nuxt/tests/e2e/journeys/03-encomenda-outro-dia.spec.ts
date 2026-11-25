import { expect, test } from '@playwright/test'
import { auditStep } from './support/audit'
import { addsFromMenu, goesToCheckout, opens, reviewsAndSends } from './support/steps'

// §5.1 · Encomendar (outro dia). A cliente quer o pão que só fica pronto amanhã: o produto
// diz o dia antes da sacola, a sacola e o checkout já vêm no dia da fornada, e o
// acompanhamento repete o mesmo dia. A variação "com a loja fechada" pede a pilha da casa
// que fecha (JOURNEYS_CLOSING_IN_MINUTES) e o relógio fixo do servidor: issue #3575.
const PRODUCT = 'Tabatière' // só tem fornada amanhã no seed `--profile qa`

test('encomendar para outro dia: a fornada de amanhã, do produto ao acompanhamento', async ({ page }, testInfo) => {
  await opens(page)
  await test.step('produto, "Encomendar para amanhã" e sacola', async () => {
    await addsFromMenu(page, testInfo, PRODUCT, 'Encomendar para amanhã')
  })
  await test.step('finalizar: retirada no dia da fornada, Pix, revisar e enviar', async () => {
    await goesToCheckout(page)
    await page.getByRole('radio', { name: /^Retirada/ }).click()
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
    await expect(page.getByRole('radio', { name: /^(Amanhã|Próxima fornada)/, checked: true })).toBeVisible()
    await page.getByRole('radio', { name: /^A partir das \d{1,2}h(\d{2})?$/ }).first().click()
    await auditStep(page, testInfo, 'finalizar-quando')
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
    await page.getByRole('radio', { name: /^Pix/ }).click()
    await reviewsAndSends(page, testInfo)
  })
  await test.step('o acompanhamento diz para quando é a encomenda', async () => {
    await expect(page.getByRole('button', { name: 'Simular pagamento' })).toBeVisible()
    await auditStep(page, testInfo, 'acompanhamento')
  })
})
