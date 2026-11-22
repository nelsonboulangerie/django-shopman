import { expect, test, type Page } from '@playwright/test'
import { addReadyProductFromMenu, checkoutSigningInByCode, paysPixOnTracking } from './support/customer'
import { capture, settled } from './support/stack'

// J10 · Cupom e pontos (#2569, item 5).
//
// Papel: quem volta, com pontos de fidelidade no seed `--profile qa`. Leva 1 Croissant
// (R$ 13,00) para hoje e, no pagamento:
//   1. tenta o PRIMEIRACOMPRA, que pede pedido mínimo de R$ 30: a loja diz por que não vale;
//   2. aplica o NELSON10 (10%): a loja diz "aplicado" e o desconto de R$ 1,30;
//   3. usa os pontos: a loja diz quanto eles cobrem;
// revisa, envia, paga, e o Pix cobra o que sobrou: R$ 13,00 − cupom − pontos.
//
// Um cliente por tamanho de tela: a mesma pessoa nos dois projetos cairia na espera de
// reenvio do código. O NELSON10 é de uso único no seed: o passo 2 roda no celular (João,
// CLI-003), e no computador (Ana, CLI-005) a jornada segue sem ele. A Maria (CLI-001) não
// entra: o seed põe o aniversário dela hoje, e os 10% de aniversário se confundiriam com o
// cupom.
const PRODUCT = 'Croissant'
const PRICE_Q = 1300
const COUPON_Q = 130
const RETURNING = {
  phone: { phone: '43993333333' },
  desktop: { phone: '43995555555' }
}
const isDesktop = (projectName: string) => projectName.includes('1366')

function brl (q: number): string {
  return `R$ ${Math.floor(q / 100)},${String(q % 100).padStart(2, '0')}`
}

function couponBox (page: Page) {
  return page.locator('[data-checkout-coupon]').first()
}

/** Tenta um cupom. Com outro já na sacola, desliga o cartão (tira o cupom) e liga de novo. */
async function triesCoupon (page: Page, code: string): Promise<void> {
  const box = couponBox(page)
  const toggle = page.locator('#checkout-coupon-toggle')
  if (!(await box.getByText('Cupom de desconto?').isVisible().catch(() => false))) {
    await toggle.click()
    await expect(box).toContainText('Cupom de desconto?')
  }
  const field = page.getByPlaceholder('Código do cupom')
  if (!(await field.isVisible().catch(() => false))) await toggle.click()
  await field.fill(code)
  await page.getByRole('button', { name: 'Aplicar', exact: true }).click()
}

test('J10: o cupom que não vale diz por quê, o que vale abate, e os pontos entram no total', async ({ page }, testInfo) => {
  test.setTimeout(300_000)
  const withValidCoupon = !isDesktop(testInfo.project.name)
  let pointsQ = 0

  await test.step('quem volta leva 1 Croissant e entra pelo código', async () => {
    await addReadyProductFromMenu(page, testInfo, PRODUCT)
    await checkoutSigningInByCode(page, testInfo, withValidCoupon ? RETURNING.phone : RETURNING.desktop)
  })

  await test.step('retirada hoje, Pix', async () => {
    await page.getByRole('radio', { name: /^Retirada/ }).click()
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
    await page.getByRole('radio', { name: /^Hoje/ }).click().catch(() => undefined)
    await page.getByRole('radio', { name: /^\d{1,2}h(\d{2})? às \d{1,2}h(\d{2})?$/ }).first().click()
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
    await page.getByRole('radio', { name: /^Pix/ }).click()
    await settled(page)
  })

  await test.step('o PRIMEIRACOMPRA não vale abaixo do mínimo, e a loja diz por quê', async () => {
    await triesCoupon(page, 'PRIMEIRACOMPRA')
    // Mínimo de R$ 30 e 1 Croissant de R$ 13: faltam R$ 17.
    await expect(page.getByText('Faltam R$ 17,00 para usar este cupom.').first()).toBeVisible()
    await expect(couponBox(page)).toContainText(/PRIMEIRACOMPRA\s*sem desconto/)
    await capture(page, testInfo, 'cupom-abaixo-do-minimo')
  })

  if (withValidCoupon) {
    await test.step('o NELSON10 vale e abate', async () => {
      await triesCoupon(page, 'NELSON10')
      await expect(couponBox(page)).toContainText(/NELSON10\s*aplicado/)
      await expect(couponBox(page)).toContainText(`Desconto de ${brl(COUPON_Q)}`)
      await capture(page, testInfo, 'cupom-aplicado')
    })
  } else {
    // No computador, sem cupom: o PRIMEIRACOMPRA sai antes dos pontos.
    await page.locator('#checkout-coupon-toggle').click()
    await expect(couponBox(page)).toContainText('Cupom de desconto?')
  }

  await test.step('os pontos entram, e a loja diz quanto cobrem', async () => {
    const points = page.getByText('Usar pontos de fidelidade')
    await expect(points).toBeVisible()
    const cover = page.getByText(/^Seus pontos cobrem até R\$ \d+,\d{2}$/).first()
    await expect(cover).toBeVisible()
    const [, reais, cents] = (await cover.innerText()).match(/R\$ (\d+),(\d{2})/)!
    pointsQ = Number(reais) * 100 + Number(cents)
    await points.click()
    await expect(page.locator('#checkout-loyalty')).toHaveAttribute('aria-checked', 'true')
    await capture(page, testInfo, 'pontos')
  })

  await test.step('revisa, envia e paga só o que sobrou', async () => {
    await page.getByRole('button', { name: 'Revisar pedido' }).click()
    if (withValidCoupon) await expect(page.getByText(/NELSON10/).last()).toBeVisible()
    await expect(page.getByText(/pontos/i).last()).toBeVisible()
    await capture(page, testInfo, 'revisar-com-cupom-e-pontos')
    await page.getByRole('button', { name: 'Enviar pedido' }).click()
    await expect(page).toHaveURL(/\/pedido\/[^/]+$/, { timeout: 60_000 })
    await settled(page)
    const dueQ = Math.max(0, PRICE_Q - (withValidCoupon ? COUPON_Q : 0) - pointsQ)
    await expect(page.getByText(brl(dueQ)).first()).toBeVisible()
    await paysPixOnTracking(page, testInfo)
  })
})
