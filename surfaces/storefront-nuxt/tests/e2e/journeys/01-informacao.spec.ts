import { expect, test } from '@playwright/test'
import { auditStep } from './support/audit'
import { hydrated } from './support/experience'
import { opens } from './support/steps'

// §5.1 · Informação sem compra. Critério: horário, endereço, formas de pagamento,
// alérgenos e entrega respondidos em até dois toques a partir da home. A cliente está
// logada porque a versão é decidida no login (D2); o mesmo vale nas duas versões.
test('informação sem compra: horário, endereço, pagamento, entrega e alérgenos em até dois toques', async ({ page }, testInfo) => {
  await opens(page)

  await test.step('a home', async () => {
    await page.goto('/')
    await hydrated(page)
    await auditStep(page, testInfo, 'home')
  })

  await test.step('horário e endereço no rodapé, sem toque', async () => {
    const footer = page.locator('footer').last()
    await footer.scrollIntoViewIfNeeded()
    await expect(footer.getByText('Horário', { exact: true })).toBeVisible()
    await auditStep(page, testInfo, 'rodape')
  })

  await test.step('as perguntas frequentes (pagamento, entrega), um toque', async () => {
    await page.goto('/')
    await hydrated(page)
    await page.locator('a[href="/faq"]:visible').first().click()
    await expect(page).toHaveURL(/\/faq$/)
    await hydrated(page)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await auditStep(page, testInfo, 'perguntas')
  })

  await test.step('alérgenos na página do produto, dois toques (cardápio, produto)', async () => {
    await page.goto('/')
    await hydrated(page)
    await page.locator('a[href="/menu"]:visible').first().click()
    await expect(page).toHaveURL(/\/menu/)
    await hydrated(page)
    await page.getByRole('link', { name: 'Croissant' }).first().click()
    await expect(page).toHaveURL(/\/produto\//)
    await hydrated(page)
    await expect(page.getByText(/^Alérgenos:/).first()).toBeAttached()
    await auditStep(page, testInfo, 'produto-alergenos')
  })
})
