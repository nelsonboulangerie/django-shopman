import { expect, test, type Page } from '@playwright/test'
import { checkoutSigningInByCode } from './support/customer'
import { capture, newCustomerPhone, settled } from './support/stack'

// J5 · Casa fechada (docs/plans/EXCELENCIA-STOREFRONT-PLANO.md, seção 8; #2686).
//
// Papel: a cliente que pede no fim do expediente para a próxima abertura. Ela monta a
// encomenda com a loja nos últimos minutos, chega à revisão, e a loja fecha com a revisão
// aberta na tela dela. A revisão diz até quando a loja confirma o pedido, e o checkout
// atravessa o fechamento: ao voltar à aba, a frase é refeita com a casa já fechada.
//
// Por que muda: o prazo da loja só corre com a casa ABERTA (business_calendar
// .next_operational_deadline). Antes do fechamento, os minutos que restam hoje entram na
// conta; depois, o prazo inteiro começa na próxima abertura. A frase velha, na tela, seria
// uma promessa que a loja não cumpre.
//
// "Hoje" não aparece nesta jornada: a meia hora de hoje pede 30 min de antecedência e
// precisa caber até o fechamento, e a casa desta pilha fecha em minutos. É a encomenda.
//
// A casa que fecha daqui a pouco é AMBIENTE da pilha: `scripts/run_storefront_journeys.sh`
// com `JOURNEYS_CLOSING_IN_MINUTES=N` passa `--closing-in-minutes N` ao seed, e só a J5 roda
// nessa pilha. Na pilha de sempre (aberta 24 h), a J5 pula e diz por quê.
const PRODUCT = 'Croissant'
const CLOSING = process.env.JOURNEY_STORE_CLOSING === '1'

/** "Últimos pedidos até 4h12" (ou "Aberto até", se faltar mais de uma hora), no alto da
 *  loja: a hora em que a casa fecha hoje, em Brasília. */
async function closingLabel (page: Page): Promise<string> {
  const label = page.getByText(/^(Aberto|Últimos pedidos) até \d{1,2}h(\d{2})?$/).first()
  await expect(label, 'a loja da pilha precisa estar aberta agora, fechando daqui a pouco').toBeVisible()
  return (await label.textContent())!.trim()
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

/** A frase do dinheiro na revisão: "A loja confirma o pedido até segunda, 23/11, às 10h55". */
const MONEY_LATER = /A loja confirma o pedido até (amanhã, [a-zç]+|[a-zç]+, \d{2}\/\d{2}), (às|à) \d{1,2}h(\d{2})?/

function moneySentence (page: Page) {
  return page.getByText(MONEY_LATER).first()
}

/** A cliente sai da aba e volta. A loja relê o checkout quando a aba VOLTA a ficar visível
 *  (useConnectivity), e um evento solto com a aba sempre visível não muda nada: a aba
 *  precisa passar por "hidden". Espera a releitura do servidor e devolve a frase nova. */
async function returnsToTab (page: Page): Promise<string> {
  const reread = page.waitForResponse(r => r.request().method() === 'GET' && /\/api\/v1\/storefront\/checkout\//.test(r.url()))
  for (const state of ['hidden', 'visible']) {
    await page.evaluate((value) => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => value })
      document.dispatchEvent(new Event('visibilitychange'))
    }, state)
  }
  await reread
  await settled(page)
  return (await moneySentence(page).textContent())!.trim()
}

test('J5: a loja fecha com a revisão aberta, e a frase do prazo é refeita', async ({ page }, testInfo) => {
  test.skip(!CLOSING, 'a J5 precisa da pilha que fecha a casa (JOURNEYS_CLOSING_IN_MINUTES no script da pilha)')
  test.setTimeout(600_000)
  const customer = { phone: newCustomerPhone(), name: 'Teresa' }

  const closes = await test.step('nos últimos minutos, a cliente encomenda para a próxima abertura', async () => {
    await page.goto('/menu')
    await settled(page)
    const closes = await closingLabel(page)
    await capture(page, testInfo, 'cardapio-ultimos-pedidos')
    await page.getByRole('link', { name: PRODUCT }).first().click()
    await expect(page).toHaveURL(/\/produto\//)
    await settled(page)
    // O que fica pronto hoje se chama "Adicionar"; o resto, "Encomendar para <dia>". Os
    // botões de "Você também pode gostar" levam o nome do outro produto no fim.
    await page.getByRole('button', { name: /^(Adicionar|Encomendar para [a-zçá]+)$/ }).first().click()
    await expect(page.getByRole('group', { name: `Quantidade de ${PRODUCT}` })).toContainText('1')
    await capture(page, testInfo, 'produto')
    await page.getByRole('link', { name: 'Sacola, 1 item', exact: true }).first().click()
    await expect(page.getByRole('heading', { name: 'Sua sacola' })).toBeVisible()
    return closes
  })

  const before = await test.step('chega à revisão com a loja ainda aberta', async () => {
    await checkoutSigningInByCode(page, testInfo, customer)
    await page.getByRole('radio', { name: /^Retirada/ }).click()
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
    // Encomenda: a grade é a do turno da casa ("A partir das 9h"), não a meia hora de hoje.
    await page.getByRole('radio', { name: /^A partir das \d{1,2}h(\d{2})?$/ }).first().click()
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
    await page.getByRole('radio', { name: /^Pix/ }).click()
    await page.getByRole('button', { name: 'Revisar pedido' }).click()
    await expect(page.getByRole('heading', { name: 'Revise seu pedido' })).toBeVisible()
    await expect(moneySentence(page)).toBeVisible()
    await page.waitForTimeout(600) // a folha da revisão termina de subir antes da captura
    await capture(page, testInfo, 'revisao-loja-aberta')
    const left = await msUntil(page, closes)
    expect(left, `a casa (${closes}) deveria fechar com a revisão aberta, e não antes`).toBeGreaterThan(0)
    return { text: (await moneySentence(page).textContent())!.trim(), left }
  })

  await test.step('a loja fecha; a cliente volta à aba e a frase é refeita com a casa fechada', async () => {
    await page.waitForTimeout(before.left + 5_000)
    // A cliente volta à aba: o checkout relê o servidor (a releitura do L05, P2-08).
    const after = await returnsToTab(page)
    expect(after, 'com a casa fechada, o prazo começa inteiro na próxima abertura').not.toBe(before.text)
    await expect(page.getByText(/A loja confirma o pedido em até \d+ minutos?/)).toHaveCount(0)
    await capture(page, testInfo, 'revisao-loja-fechada')
    // Prova de que a casa fechou para o servidor: aberta, o prazo anda com o relógio (os
    // minutos que restam hoje encolhem); fechada, ele fica parado na próxima abertura.
    await page.waitForTimeout(65_000)
    expect(await returnsToTab(page), 'com a casa fechada, o prazo não anda com o relógio').toBe(after)
    testInfo.annotations.push(
      { type: 'antes do fechamento', description: before.text },
      { type: 'depois do fechamento', description: after },
    )
  })

  await test.step('envia a encomenda com a casa fechada', async () => {
    await page.getByRole('button', { name: 'Enviar pedido' }).click()
    await expect(page).toHaveURL(/\/pedido\/[^/]+$/, { timeout: 60_000 })
    await settled(page)
    await capture(page, testInfo, 'acompanhamento')
  })
})
