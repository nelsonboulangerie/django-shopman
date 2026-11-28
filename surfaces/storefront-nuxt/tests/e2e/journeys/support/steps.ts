import { expect, type Page, type TestInfo } from '@playwright/test'
import { auditStep } from './audit'
import { expectServerVariant, hydrated, startsWithEmptyBag } from './experience'

// Os gestos da cliente que mais de uma jornada repete, cada um com a auditoria do passo.
// São os mesmos nas duas versões: a jornada é escrita uma vez, e a versão é a que o
// servidor decidiu para a sessão (support/experience.ts confere no começo de cada uma).

/** Abertura comum: sacola vazia e a versão do servidor conferida. */
export async function opens (page: Page): Promise<void> {
  await startsWithEmptyBag(page)
  await expectServerVariant(page)
}

/** Cardápio → produto → "Adicionar" (ou outro rótulo de ação, como "Encomendar para
 *  amanhã") → sacola, auditando cada tela. */
export async function addsFromMenu (page: Page, testInfo: TestInfo, product: string, action = 'Adicionar'): Promise<void> {
  await page.goto('/menu')
  await hydrated(page)
  await expect(page.getByRole('link', { name: product }).first()).toBeVisible()
  await auditStep(page, testInfo, 'cardapio')

  await page.getByRole('link', { name: product }).first().click()
  await expect(page).toHaveURL(/\/produto\//)
  await hydrated(page)
  await expect(page.getByRole('heading', { name: product, level: 1 })).toBeVisible()
  await auditStep(page, testInfo, 'produto')

  await page.getByRole('button', { name: action, exact: true }).first().click()
  await expect(page.getByRole('group', { name: `Quantidade de ${product}` }).first()).toContainText('1')
  await page.getByRole('link', { name: /^Sacola, \d+ ite(m|ns)$/ }).first().click()
  await expect(page.getByRole('heading', { name: 'Sua sacola' })).toBeVisible()
  await hydrated(page)
  await auditStep(page, testInfo, 'sacola')
}

/** Da sacola ao checkout: a cliente já entrou, então a loja abre direto o finalizar. */
export async function goesToCheckout (page: Page): Promise<void> {
  await page.getByRole('link', { name: 'Finalizar pedido' }).last().click()
  await expect(page).toHaveURL(/\/finalizar/)
  await hydrated(page)
}

/** Retirada hoje, primeiro horário, Pix; revisa e envia. Devolve o código do pedido. */
export async function placesPickupTodayWithPix (page: Page, testInfo: TestInfo, audit = true): Promise<string> {
  await page.getByRole('radio', { name: /^Retirada/ }).click()
  if (audit) await auditStep(page, testInfo, 'finalizar-recebimento')
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  await expect(page.getByText('Horário da retirada')).toBeVisible()
  await page.getByRole('radio', { name: /^Hoje/ }).click().catch(() => undefined)
  await page.getByRole('radio', { name: /^\d{1,2}h(\d{2})? às \d{1,2}h(\d{2})?$/ }).first().click()
  if (audit) await auditStep(page, testInfo, 'finalizar-horario')
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  await page.getByRole('radio', { name: /^Pix/ }).click()
  if (audit) await auditStep(page, testInfo, 'finalizar-pagamento')
  return await reviewsAndSends(page, testInfo, audit)
}

/** "Revisar pedido" → a folha da revisão → "Enviar pedido" → acompanhamento. */
export async function reviewsAndSends (page: Page, testInfo: TestInfo, audit = true): Promise<string> {
  await page.getByRole('button', { name: 'Revisar pedido' }).click()
  await expect(page.getByRole('heading', { name: 'Revise seu pedido' })).toBeVisible()
  // A folha da revisão é um diálogo: trocar de largura com ele aberto mede outra coisa.
  if (audit) await auditStep(page, testInfo, 'revisar', { widths: ['375'] })
  await page.getByRole('button', { name: 'Enviar pedido' }).click()
  await expect(page).toHaveURL(/\/pedido\/[^/]+$/, { timeout: 60_000 })
  await hydrated(page)
  return decodeURIComponent(new URL(page.url()).pathname.split('/').pop()!)
}
