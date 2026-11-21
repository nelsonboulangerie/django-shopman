import { expect, test } from '@playwright/test'
import { checkoutSigningInByCode, paysPixOnTracking } from './support/customer'
import { capture, newCustomerPhone, settled } from './support/stack'

// J2 · A encomenda da fornada de amanhã (docs/plans/EXCELENCIA-STOREFRONT-PLANO.md, seção 8;
// WP-L02).
//
// Papel: a cliente nova que quer o pão que só sai amanhã. A página do produto diz o dia e a
// hora antes de ela montar a sacola, o botão é "Encomendar para amanhã", a sacola e o
// checkout já vêm no dia da fornada (ela não escolhe uma data em que o pão não existe), e o
// pedido sai com Pix e chega ao acompanhamento com o mesmo dia.
//
// O que a jornada supõe do seed `--profile qa`: a Tabatière só tem fornada amanhã (a vitrine
// do perfil), e a loja da pilha está aberta.
const PRODUCT = 'Tabatière'
// Sem âncora: o parágrafo começa com o ícone do relógio, e a loja usa espaço inseparável.
const PROMISE_TOMORROW = /Fica\s+pronto\s+amanhã,\s+[a-zçá]+,\s+a\s+partir\s+das\s+\d{1,2}h(\d{2})?/

test('J2: a encomenda da fornada de amanhã, do produto ao acompanhamento', async ({ page }, testInfo) => {
  test.setTimeout(300_000)
  const customer = { phone: newCustomerPhone(), name: 'Helena' }

  await test.step('o produto diz quando fica pronto, antes de ela montar a sacola', async () => {
    await page.goto('/menu')
    await settled(page)
    await expect(page.getByText(/^(Aberto|Últimos pedidos)\b/).first(), 'a loja da pilha precisa estar aberta agora').toBeVisible()
    await page.getByRole('link', { name: PRODUCT }).first().click()
    await expect(page).toHaveURL(/\/produto\//)
    await settled(page)
    await expect(page.getByRole('heading', { name: PRODUCT, level: 1 })).toBeVisible()
    await expect(page.locator('[data-pdp-ready-promise]')).toContainText(PROMISE_TOMORROW)
    await capture(page, testInfo, 'produto-amanha')
  })

  await test.step('"Encomendar para amanhã" põe na sacola, e a sacola diz o mesmo dia', async () => {
    await page.getByRole('button', { name: 'Encomendar para amanhã', exact: true }).first().click()
    await expect(page.getByRole('group', { name: `Quantidade de ${PRODUCT}` })).toContainText('1')
    await page.getByRole('link', { name: 'Sacola, 1 item', exact: true }).first().click()
    await expect(page.getByRole('heading', { name: 'Sua sacola' })).toBeVisible()
    await expect(page.locator('main')).toContainText(PROMISE_TOMORROW)
    await capture(page, testInfo, 'sacola-amanha')
  })

  const day = await test.step('no checkout, o Quando já está no dia da fornada', async () => {
    await checkoutSigningInByCode(page, testInfo, customer)
    await page.getByRole('radio', { name: /^Retirada/ }).click()
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
    // O dia vem marcado: "Amanhã" (ou "Próxima fornada", se amanhã a casa não abre).
    const chosen = page.getByRole('radio', { name: /^(Amanhã|Próxima fornada)/, checked: true })
    await expect(chosen).toBeVisible()
    // Hoje não serve: o pão só existe amanhã. Se a opção aparece, aparece desligada.
    const today = page.getByRole('radio', { name: /^Hoje/ })
    if (await today.count()) await expect(today.first()).toBeDisabled()
    // Turno da casa; o que começa antes de o pão ficar pronto vem riscado, com o motivo.
    await page.getByRole('radio', { name: /^A partir das \d{1,2}h(\d{2})?$/ }).first().click()
    await capture(page, testInfo, 'quando-amanha')
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
    await page.getByRole('radio', { name: /^Pix/ }).click()
    await page.getByRole('button', { name: 'Revisar pedido' }).click()
    await expect(page.getByRole('heading', { name: 'Revise seu pedido' })).toBeVisible()
    // "Retirada · Amanhã · A partir das 15h" (ou "dom, 22/11", quando a fornada não é amanhã).
    const pickup = /Retirada\s*·\s*(Amanhã|[a-zá]{3},\s*\d{2}\/\d{2})\s*·\s*A\s+partir\s+das\s+\d{1,2}h(\d{2})?/
    const review = page.getByRole('dialog').filter({ has: page.getByRole('heading', { name: 'Revise seu pedido' }) })
    await expect(review).toContainText(pickup)
    await page.waitForTimeout(600) // a folha da revisão termina de subir antes da captura
    await capture(page, testInfo, 'revisao-amanha')
    return (await review.textContent())!.match(pickup)![1]!
  })

  await test.step('envia, paga o Pix, e o acompanhamento diz o mesmo dia', async () => {
    await page.getByRole('button', { name: 'Enviar pedido' }).click()
    await expect(page).toHaveURL(/\/pedido\/[^/]+$/, { timeout: 60_000 })
    await settled(page)
    await paysPixOnTracking(page, testInfo)
    // O mesmo dia, dito como o acompanhamento diz: "amanhã" ou a data (dd/mm) de amanhã,
    // medida no navegador, que roda no fuso da loja.
    const tomorrow = await page.evaluate(() => {
      const d = new Date()
      d.setDate(d.getDate() + 1)
      return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`
    })
    const sameDay = day === 'Amanhã' ? new RegExp(`amanhã|${tomorrow}`, 'i') : new RegExp(day.match(/\d{2}\/\d{2}/)![0].replace('/', '\\/'))
    await expect(page.locator('main'), `o acompanhamento deveria dizer o dia da fornada (${day})`).toContainText(sameDay)
    await capture(page, testInfo, 'acompanhamento-amanha')
  })
})
