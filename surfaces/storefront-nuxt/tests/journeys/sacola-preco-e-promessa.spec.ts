import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { capture, settled } from './support/stack'

// A sacola fala a mesma promessa, e o preço fecha (WP-L03 do plano
// docs/plans/EXCELENCIA-STOREFRONT-PLANO.md; achados P1-05, P2-02 e P2-12).
//
// Papel: a cliente, ainda sem entrar (a sacola não pede identificação). Ela põe na sacola
// um pão em promoção que só fica pronto amanhã e um item pronto agora, e lê a sacola: cada
// linha tem um preço só (o que ela paga, com o cheio riscado quando há promoção), a linha
// da fornada diz quando fica pronta, o alto da sacola diz para quando fica o pedido, e o
// resumo fecha com as linhas. Um pedido tem uma data só: com a Tabatière de amanhã na sacola,
// o Croissant também fica para amanhã, e a linha dele diz isso.
//
// O que a jornada supõe do seed `--profile qa`: a Tabatière está na promoção "Semana do
// Pão" (15% nos rústicos, por 7 dias a partir do seed) e só tem fornada amanhã; o Croissant
// está pronto na vitrine. Com o seed mais velho que 7 dias, a promoção venceu e a jornada
// reprova no primeiro passo, dizendo isso.
const BATCH_PRODUCT = 'Tabatière'
const READY_PRODUCT = 'Croissant'

function cents (money: string): number {
  const match = money.match(/R\$\s*([\d.]+),(\d{2})/)
  if (!match) throw new Error(`valor não reconhecido: "${money}"`)
  return Number(match[1]!.replace(/\./g, '')) * 100 + Number(match[2])
}

async function addFromProductPage (page: Page, testInfo: TestInfo, product: string, addButton: RegExp): Promise<void> {
  await page.goto('/menu')
  await settled(page)
  await page.getByRole('link', { name: product }).first().click()
  await expect(page).toHaveURL(/\/produto\//)
  await settled(page)
  await expect(page.getByRole('heading', { name: product, level: 1 })).toBeVisible()
  // A tela mostra a quantidade na hora; a sacola só existe quando o servidor responde, e
  // sair da página antes disso aborta a escrita.
  const written = page.waitForResponse(response => /\/cart\//.test(response.url()) && response.request().method() !== 'GET' && response.ok())
  await page.getByRole('button', { name: addButton }).first().click()
  await written
  await expect(page.getByRole('group', { name: `Quantidade de ${product}` })).toContainText('1')
  await capture(page, testInfo, `produto-${product.toLowerCase().normalize('NFD').replace(/[^a-z]/g, '')}`)
}

test('a sacola diz quando fica pronto e o preço fecha com o resumo', async ({ page }, testInfo) => {
  await test.step('a cliente encomenda o pão em promoção que só fica pronto amanhã', async () => {
    await addFromProductPage(page, testInfo, BATCH_PRODUCT, /^Encomendar para /)
  })

  await test.step('e põe na sacola um item pronto agora', async () => {
    await addFromProductPage(page, testInfo, READY_PRODUCT, /^Adicionar$/)
  })

  await test.step('a cliente abre a sacola', async () => {
    await page.goto('/sacola')
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Sua sacola' })).toBeVisible()
    await expect(page.locator('[data-cart-line-item]')).toHaveCount(2)
  })

  const batchLine = page.locator('[data-cart-line-item]', { hasText: BATCH_PRODUCT })
  const readyLine = page.locator('[data-cart-line-item]', { hasText: READY_PRODUCT })

  await test.step('a linha em promoção mostra o preço que ela paga, com o cheio riscado', async () => {
    await expect(
      batchLine.locator('[data-line-total-struck]'),
      'a Tabatière precisa estar na promoção Semana do Pão (seed qa com menos de 7 dias)'
    ).toBeVisible()
    await expect(batchLine.locator('[data-cart-line-price]')).toContainText(/1 × R\$ \d+,\d{2} cada, antes R\$ \d+,\d{2}/)
    const paid = cents(await batchLine.locator('[data-line-total-value]').innerText())
    const full = cents(await batchLine.locator('[data-line-total-struck]').innerText())
    expect(paid).toBeLessThan(full)
    // O unitário com desconto é o mesmo valor do total da linha (uma unidade): a linha
    // não fala dois preços (P1-05).
    expect(cents(await batchLine.locator('[data-cart-line-price]').innerText())).toBe(paid)
    // O item sem promoção tem um valor só, sem risco.
    await expect(readyLine.locator('[data-line-total-struck]')).toHaveCount(0)
  })

  await test.step('a linha da fornada diz quando fica pronta, e o alto da sacola diz para quando fica o pedido', async () => {
    await expect(batchLine.locator('[data-cart-line-promise]')).toContainText(/Disponível .+, a partir das \d{1,2}h(\d{2})?$/)
    // O Croissant, pronto na vitrine, vai junto no pedido de amanhã: a linha dele diz o dia.
    await expect(readyLine.locator('[data-cart-line-promise]')).toContainText(/Disponível /)
    await expect(page.locator('[data-cart-ready-line]')).toContainText(/Seu pedido fica pronto .+, a partir das \d{1,2}h(\d{2})?\.$/)
    // O selo e a frase antigos saíram da sacola: a promessa do servidor diz o dia e a hora.
    await expect(page.getByText('Lista de espera')).toHaveCount(0)
    await expect(page.getByText(/^Previsto para/)).toHaveCount(0)
  })

  await test.step('o resumo fecha com as linhas', async () => {
    const lineTotals = await page.locator('[data-cart-line-item] [data-line-total-value]').allInnerTexts()
    const sum = lineTotals.reduce((total, text) => total + cents(text), 0)
    const subtotal = page.locator('[data-summary-subtotal]').first()
    expect(cents(await subtotal.innerText())).toBe(sum)
    await expect(page.locator('[data-summary-promo-savings]').first()).toContainText(/^Já com R\$ \d+,\d{2} de desconto em promoções\.$/)
    await page.locator('[data-summary-subtotal]').first().scrollIntoViewIfNeeded()
    await capture(page, testInfo, 'sacola-resumo')
    await page.getByRole('heading', { name: 'Sua sacola' }).scrollIntoViewIfNeeded()
    await capture(page, testInfo, 'sacola')
  })
})
