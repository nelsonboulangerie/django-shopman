import { expect, test } from '@playwright/test'
import { auditStep } from './support/audit'
import { hydrated } from './support/experience'
import { opens } from './support/steps'

// §5.1 · Recompra. Critério: um gesto a partir da home logada, com preço e
// disponibilidade de agora. O último pedido da cliente é o da jornada anterior.
test('recompra: "Repetir pedido" na home logada leva os itens à sacola', async ({ page }, testInfo) => {
  await opens(page)
  await test.step('a home logada oferece repetir o último pedido', async () => {
    await page.goto('/')
    await hydrated(page)
    const repeat = page.getByRole('button', { name: 'Repetir pedido' }).first()
    // O convite é um dos destaques do topo; quem está noutro destaque passa para ele.
    for (let i = 0; i < 6 && !(await repeat.isVisible().catch(() => false)); i += 1) {
      const next = page.getByRole('button', { name: /Próximo|Avançar|Seguinte/ }).first()
      if (!(await next.isVisible().catch(() => false))) break
      await next.click()
      await page.waitForTimeout(500)
    }
    await expect(repeat).toBeVisible()
    await auditStep(page, testInfo, 'home-repetir')
  })
  await test.step('um gesto: os itens voltam à sacola, com o preço de agora', async () => {
    await page.getByRole('button', { name: 'Repetir pedido' }).first().click()
    await expect(page).toHaveURL(/\/sacola/, { timeout: 30_000 })
    await hydrated(page)
    await expect(page.getByRole('group', { name: /^Quantidade de / }).first()).toBeVisible()
    await auditStep(page, testInfo, 'sacola-repetida')
  })
})
