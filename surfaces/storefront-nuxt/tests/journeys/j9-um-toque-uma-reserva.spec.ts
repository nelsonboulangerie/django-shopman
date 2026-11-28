import { expect, test, type Browser, type Page } from '@playwright/test'
import { capture, settled, stack } from './support/stack'

// J9 · Um toque, uma reserva (docs/plans/EXCELENCIA-STOREFRONT-PLANO.md, seções 7 e 8; #2573).
//
// Papéis: a cliente nova A, que toca uma vez em "Adicionar" com a loja lenta, e a cliente B,
// que vem depois e mede quanto sobrou. A resposta da primeira escrita de A chega ao BFF
// depois do prazo dele (o Django já gravou): sem a semente de sessão do WP-L08, a nova
// tentativa caía noutra sessão e o pão ficava reservado duas vezes, uma delas numa sacola
// que ninguém vê.
//
// A lentidão é AMBIENTE da pilha, não estado: um proxy só de teste fica entre a loja e o
// Django (`support/slow-proxy.mjs`, README do e2e, seção 3) e atrasa UMA resposta. Sem o
// proxy na pilha, a jornada pula e diz por quê.
//
// Como se mede "uma reserva" pela tela: o Melonpan mostra 2 unidades à loja online (seed
// `--profile qa`, últimas unidades). Se A segura exatamente uma, B leva a outra e o "+" dela
// já chega ao teto. Se A segurasse duas, B não levaria nenhuma.
const PRODUCT = 'Melonpan'
const PRODUCT_PATH = '/produto/MELON'
const PROXY = process.env.JOURNEY_PROXY_CONTROL?.replace(/\/$/, '')

function addButton (page: Page) {
  return page.getByRole('button', { name: 'Adicionar', exact: true }).first()
}

function quantityOf (page: Page) {
  return page.getByRole('group', { name: `Quantidade de ${PRODUCT}` }).first()
}

async function slowProxy (path: string, body: Record<string, unknown> = {}) {
  const res = await fetch(`${PROXY}/__slow-proxy/${path}`, { method: 'POST', body: JSON.stringify(body) })
  expect(res.ok, `o proxy lento da pilha respondeu ${res.status}`).toBe(true)
}

async function opensProduct (page: Page) {
  await page.goto(PRODUCT_PATH)
  await settled(page)
  await expect(page.getByRole('heading', { name: PRODUCT, level: 1 })).toBeVisible()
}

/** Nada fica preso na sacola de ninguém: a próxima rodada começa com as 2 unidades. */
async function leavesNothingBehind (page: Page) {
  try {
    await page.goto('/sacola')
    await settled(page)
    const trash = page.getByRole('button', { name: `Remover ${PRODUCT}`, exact: true }).first()
    if (await trash.count()) await trash.click({ timeout: 5_000 })
  } catch {
    // A pilha caiu ou a página não abriu: o relatório já diz o que houve.
  }
}

async function otherCustomer (browser: Browser) {
  const context = await browser.newContext({ baseURL: stack.store, viewport: { width: 1366, height: 768 }, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' })
  return { context, page: await context.newPage() }
}

test('J9: um toque em Adicionar com a loja lenta deixa uma unidade na sacola e uma reserva só', async ({ page, browser }, testInfo) => {
  test.skip(!PROXY, 'a J9 precisa do proxy lento na pilha (JOURNEY_PROXY_CONTROL; README do e2e, seção 3)')
  test.setTimeout(240_000)
  const other = await otherCustomer(browser)
  try {
    await slowProxy('reset')

    await test.step('A, cliente nova, toca uma vez em Adicionar e a resposta passa do prazo do BFF', async () => {
      await opensProduct(page)
      await expect(addButton(page)).toBeVisible()
      // A próxima escrita da sacola volta do Django 30 s depois: o BFF desiste aos 25 s.
      await slowProxy('delay', { method: 'PUT', path: '^/api/v1/cart/skus/', ms: 30_000, times: 1 })
      await addButton(page).click()
      await capture(page, testInfo, 'a-toque-com-a-loja-lenta')
    })

    await test.step('a sacola de A tem uma unidade', async () => {
      // Passado o prazo do BFF e a resposta atrasada, a sacola é a verdade do servidor.
      await page.waitForTimeout(32_000)
      await page.goto('/sacola')
      await settled(page)
      await expect(quantityOf(page)).toContainText('1')
      await capture(page, testInfo, 'a-sacola-com-uma')
    })

    await test.step('B leva a outra unidade e chega ao teto: A segura uma reserva só', async () => {
      await opensProduct(other.page)
      await addButton(other.page).click()
      await expect(quantityOf(other.page)).toContainText('1')
      await expect(
        other.page.getByRole('button', { name: `Máximo disponível de ${PRODUCT}: 1` }).first(),
        'B deveria ver o teto em 1: a outra unidade é a reserva de A'
      ).toBeVisible()
      await capture(other.page, testInfo, 'b-no-teto')
    })
  } finally {
    if (PROXY) await slowProxy('reset').catch(() => undefined)
    await leavesNothingBehind(other.page)
    await leavesNothingBehind(page)
    await other.context.close()
  }
})
