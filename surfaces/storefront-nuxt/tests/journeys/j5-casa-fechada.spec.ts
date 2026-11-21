import { expect, test, type Page } from '@playwright/test'
import { addReadyProductFromMenu, checkoutSigningInByCode } from './support/customer'
import { capture, newCustomerPhone, settled } from './support/stack'

// J5 · Casa fechada (docs/plans/EXCELENCIA-STOREFRONT-PLANO.md, seção 8; #2686).
//
// Papel: a cliente que pede no fim do expediente. Ela abre o checkout com a loja aberta, e a
// loja fecha com o checkout aberto na tela dela. O checkout atravessa o fechamento: o "Hoje"
// some das datas sem recarregar a página, e a revisão diz quando a loja confirma o pedido
// (na próxima abertura), em vez de prometer minutos que a casa fechada não tem.
//
// A casa que fecha daqui a pouco é AMBIENTE da pilha: `scripts/run_storefront_journeys.sh`
// com `JOURNEYS_CLOSING_IN_MINUTES=N` passa `--closing-in-minutes N` ao seed, e só a J5 roda
// nessa pilha. Na pilha de sempre (aberta 24 h), a J5 pula e diz por quê.
const PRODUCT = 'Croissant'
const CLOSING = process.env.JOURNEY_STORE_CLOSING === '1'

/** "Últimos pedidos até 4h12" (ou "Aberto até", se faltar mais de uma hora), no alto da
 *  loja: a hora em que a casa fecha hoje, em Brasília. */
async function closingLabel (page: Page): Promise<string> {
  return (await page.getByText(/^(Aberto|Últimos pedidos) até \d{1,2}h(\d{2})?$/).first().textContent())!.trim()
}

/** Quanto falta até a hora do rótulo, medido no NAVEGADOR (fuso da loja, `timezoneId` da
 *  config), nunca no relógio da máquina que roda a suíte (UTC na CI). */
async function msUntil (page: Page, label: string): Promise<number> {
  const [, hour, minute] = label.match(/(\d{1,2})h(\d{2})?/)!
  return page.evaluate(([h, m]) => {
    const at = new Date()
    at.setHours(h, m, 0, 0)
    return at.getTime() - Date.now()
  }, [Number(hour), Number(minute || 0)] as const)
}

const MONEY_LATER = /A loja confirma o pedido até (amanhã, [a-zç]+|[a-zç]+, \d{2}\/\d{2}), (às|à) \d{1,2}h(\d{2})?/

test('J5: a loja fecha com o checkout aberto, e a revisão diz quando ela confirma', async ({ page }, testInfo) => {
  test.skip(!CLOSING, 'a J5 precisa da pilha que fecha a casa (JOURNEYS_CLOSING_IN_MINUTES no script da pilha)')
  test.setTimeout(600_000)
  const customer = { phone: newCustomerPhone(), name: 'Teresa' }

  const closes = await test.step('a cliente põe um item na sacola com a loja aberta', async () => {
    await addReadyProductFromMenu(page, testInfo, PRODUCT)
    return await closingLabel(page)
  })

  await test.step('abre o checkout ainda com a loja aberta: retirada, hoje', async () => {
    await checkoutSigningInByCode(page, testInfo, customer)
    await page.getByRole('radio', { name: /^Retirada/ }).click()
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
    await expect(page.getByRole('radio', { name: /^Hoje/ })).toBeVisible()
    await capture(page, testInfo, 'checkout-aberto-hoje')
  })

  await test.step('a loja fecha com o checkout aberto na tela', async () => {
    const left = await msUntil(page, closes)
    expect(left, `a casa (${closes}) deveria fechar depois de a cliente abrir o checkout`).toBeGreaterThan(0)
    await page.waitForTimeout(left + 20_000)
    // A cliente volta à aba: a página relê o checkout (a mesma releitura do L05, P2-08).
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')))
    await expect(page.getByRole('radio', { name: /^Hoje/ }), 'o "Hoje" deveria sair com a casa fechada').toHaveCount(0, { timeout: 30_000 })
    await capture(page, testInfo, 'checkout-depois-do-fechamento')
  })

  await test.step('escolhe a próxima abertura e a revisão diz quando a loja confirma', async () => {
    await page.getByRole('radio', { name: /^\d{1,2}h(\d{2})? às \d{1,2}h(\d{2})?$/ }).first().click()
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
    await page.getByRole('radio', { name: /^Pix/ }).click()
    await page.getByRole('button', { name: 'Revisar pedido' }).click()
    await expect(page.getByText(MONEY_LATER).first()).toBeVisible()
    await expect(page.getByText(/A loja confirma o pedido em até \d+ minutos?/)).toHaveCount(0)
    await capture(page, testInfo, 'revisao-confirma-na-abertura')
    await settled(page)
  })
})
