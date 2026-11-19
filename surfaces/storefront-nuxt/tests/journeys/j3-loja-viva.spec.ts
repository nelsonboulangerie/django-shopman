import { expect, test, type Browser, type BrowserContext, type Page } from '@playwright/test'
import { capture, settled, stack } from './support/stack'

// J3 · Loja viva (docs/plans/EXCELENCIA-STOREFRONT-PLANO.md, WP-L04).
//
// Papéis: duas clientes na loja, cada uma no seu navegador. A fica olhando o produto das
// últimas unidades; B leva as últimas para a sacola. A página de A não é recarregada em
// momento nenhum, e a suíte prova isso com uma marca na janela: o que mudar nela chegou
// sozinho.
//
// São três caminhos para a mesma verdade, e os três têm de fechar:
// 1. o aviso da vitrine chega e a página vira "Indisponível" em segundos;
// 2. com o aviso derrubado, a consulta de reserva faz o mesmo em cerca de um minuto;
// 3. se A tocar antes de a tela mudar, a loja avisa, e ao fechar o aviso a página já está certa.
//
// B devolve os itens no fim de cada caminho (esvazia a sacola, como uma cliente faria), e a
// página de A volta a oferecer o produto, também sozinha. Por isso a jornada pode rodar de
// novo, nas duas larguras, sem refazer o seed.
const PRODUCT = 'Melonpan' // "últimas unidades" no seed `--profile qa`: 2 visíveis à loja online
const PRODUCT_PATH = '/produto/MELON'
const LAST_UNITS = 2

type Marked = Window & { __j3SameVisit?: boolean }

function addButton (page: Page) {
  return page.getByRole('button', { name: 'Adicionar', exact: true }).first()
}

async function opensProduct (page: Page): Promise<void> {
  await page.goto(PRODUCT_PATH)
  await settled(page)
  await expect(page.getByRole('heading', { name: PRODUCT, level: 1 })).toBeVisible()
}

/** A marca fica na janela: se a página recarregar, ela some e a jornada reprova. */
async function marksTheVisit (page: Page): Promise<void> {
  await page.evaluate(() => { (window as Marked).__j3SameVisit = true })
}

async function stillTheSameVisit (page: Page): Promise<void> {
  expect(await page.evaluate(() => (window as Marked).__j3SameVisit), 'a página de A foi recarregada').toBe(true)
}

async function otherCustomer (browser: Browser): Promise<{ context: BrowserContext, page: Page }> {
  const context = await browser.newContext({ baseURL: stack.store, viewport: { width: 1366, height: 768 }, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' })
  return { context, page: await context.newPage() }
}

/** A sacola respondeu: a quantidade na tela é otimista, e a reserva só existe depois da
 *  resposta do servidor. Sem esperar por ela, A pode tocar antes de B ter levado de fato. */
function bagAnswered (page: Page) {
  return page.waitForResponse(response => /\/cart\//.test(response.url()) && response.request().method() !== 'GET' && response.ok())
}

/** B põe as últimas unidades na sacola, pela página do produto. */
async function takesTheLastUnits (page: Page): Promise<void> {
  await opensProduct(page)
  let answered = bagAnswered(page)
  await addButton(page).click()
  await answered
  const quantity = page.getByRole('group', { name: `Quantidade de ${PRODUCT}` }).first()
  await expect(quantity).toContainText('1')
  for (let qty = 2; qty <= LAST_UNITS; qty += 1) {
    answered = bagAnswered(page)
    await quantity.getByRole('button', { name: `Aumentar ${PRODUCT}` }).click()
    await answered
    await expect(quantity).toContainText(String(qty))
  }
}

/** B desiste: tira o produto da sacola (a lixeira da linha), e as unidades voltam à vitrine. */
async function putsThemBack (page: Page): Promise<void> {
  await page.goto('/sacola')
  await settled(page)
  await page.getByRole('button', { name: `Remover ${PRODUCT}`, exact: true }).first().click()
  await expect(page.getByRole('group', { name: `Quantidade de ${PRODUCT}` })).toHaveCount(0)
}

/** Ao fim de cada caminho, mesmo quando ele reprova: nada fica preso na sacola de ninguém,
 *  senão o caminho seguinte começa com o produto já indisponível. */
async function leavesNothingBehind (page: Page): Promise<void> {
  try {
    await page.goto('/sacola')
    await settled(page)
    const trash = page.getByRole('button', { name: `Remover ${PRODUCT}`, exact: true }).first()
    if (await trash.count()) await trash.click({ timeout: 5_000 })
  } catch {
    // A pilha caiu ou a página não abriu: o relatório do caminho já diz o que houve.
  }
}

async function showsUnavailable (page: Page, timeout: number): Promise<void> {
  await expect(addButton(page), 'o botão de adicionar deveria ter saído sozinho').toHaveCount(0, { timeout })
  await expect(page.getByText('Indisponível', { exact: true }).first()).toBeVisible()
}

async function offersAgain (page: Page, timeout: number): Promise<void> {
  await expect(addButton(page), 'o produto deveria voltar a ser oferecido sozinho').toBeVisible({ timeout })
}

test('J3: o produto que acaba muda sozinho na tela de quem está olhando', async ({ page, browser }, testInfo) => {
  const other = await otherCustomer(browser)
  try {
    await test.step('A abre o produto das últimas unidades', async () => {
      await opensProduct(page)
      await expect(addButton(page)).toBeVisible()
      await marksTheVisit(page)
      await capture(page, testInfo, 'a-ultimas-unidades')
    })

    await test.step('B leva as últimas; a tela de A vira "Indisponível" em segundos', async () => {
      await takesTheLastUnits(other.page)
      await showsUnavailable(page, 20_000)
      await stillTheSameVisit(page)
      await capture(page, testInfo, 'a-indisponivel-sozinha')
    })

    await test.step('B desiste; o produto volta à tela de A, também sozinho', async () => {
      await putsThemBack(other.page)
      await offersAgain(page, 20_000)
      await stillTheSameVisit(page)
      await capture(page, testInfo, 'a-voltou-sozinha')
    })
  } finally {
    await leavesNothingBehind(other.page)
    await leavesNothingBehind(page)
    await other.context.close()
  }
})

test('J3: com o aviso derrubado, a consulta de reserva corrige a tela em cerca de um minuto', async ({ page, browser }, testInfo) => {
  test.setTimeout(420_000)
  // O aviso não chega a esta cliente: rede que bloqueia o stream, proxy que o segura.
  await page.route('**/sse/loja', route => route.abort())
  const other = await otherCustomer(browser)
  try {
    await opensProduct(page)
    await expect(addButton(page)).toBeVisible()
    await marksTheVisit(page)

    await takesTheLastUnits(other.page)
    await showsUnavailable(page, 90_000)
    await stillTheSameVisit(page)
    await capture(page, testInfo, 'a-indisponivel-pela-reserva')

    await putsThemBack(other.page)
    await offersAgain(page, 90_000)
    await stillTheSameVisit(page)
  } finally {
    await leavesNothingBehind(other.page)
    await leavesNothingBehind(page)
    await other.context.close()
  }
})

test('J3: se A tocar antes de a tela mudar, o aviso aparece e a página fica certa por baixo', async ({ page, browser }, testInfo) => {
  // Sem o aviso da vitrine, para a tela de A ainda estar velha na hora do toque.
  await page.route('**/sse/loja', route => route.abort())
  const other = await otherCustomer(browser)
  try {
    await opensProduct(page)
    await expect(addButton(page)).toBeVisible()
    await marksTheVisit(page)

    await takesTheLastUnits(other.page)
    await addButton(page).click()

    const notice = page.getByText('Ficou indisponível enquanto você escolhia.').first()
    await expect(notice).toBeVisible()
    await capture(page, testInfo, 'a-aviso-de-indisponivel')
    await page.keyboard.press('Escape')
    await expect(notice).toBeHidden()

    // A recusa já corrigiu a página: nada de "Adicionar" morto esperando outro toque.
    await showsUnavailable(page, 5_000)
    await stillTheSameVisit(page)
    await capture(page, testInfo, 'a-pagina-certa-depois-do-aviso')

    await putsThemBack(other.page)
  } finally {
    await leavesNothingBehind(other.page)
    await leavesNothingBehind(page)
    await other.context.close()
  }
})
