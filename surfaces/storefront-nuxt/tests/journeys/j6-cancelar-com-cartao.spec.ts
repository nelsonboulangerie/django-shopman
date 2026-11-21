import { expect, test } from '@playwright/test'
import { addReadyProductFromMenu, cancelsOnTracking, checkoutSigningInByCode, placePickupTodayPayingByCard } from './support/customer'
import { acceptsNewOrder, acknowledgeOtherOrdersAlarms, managerSignsIn } from './support/operator'
import { capture, gestorViewport, newCustomerPhone, stack } from './support/stack'

// J6 · Cancelar antes do preparo, com cartão (docs/plans/EXCELENCIA-STOREFRONT-PLANO.md,
// seção 8; #2986).
//
// Papéis: a cliente que paga com cartão e a operadora no Gestor. A régua do dono (06/11):
// "Se for antes [do preparo], cancelamos e reembolsamos." O cartão tem dois momentos antes
// do preparo, e cada um diz uma coisa diferente sobre o dinheiro:
//
//   A. a loja ainda não aceitou: o cartão está só RESERVADO, e cancelar desfaz a reserva.
//      Nada foi cobrado.
//   B. a loja aceitou: o aceite CAPTUROU a cobrança, e cancelar estorna no cartão.
//
// O cartão vai ao Stripe FALSO da pilha (`shopman/shop/tests/e2e/fake_stripe.py`): o
// adapter de produção roda inteiro, e é o fake que anula a autorização (A) e estorna o
// capturado (B). Sem a F-7 (#2568), as duas chamadas morriam no fake.
const PRODUCT = 'Croissant' // pronto agora no seed `--profile qa`

test('J6-A: cancela com o cartão só reservado, e a reserva é desfeita', async ({ page }, testInfo) => {
  test.setTimeout(240_000)
  const customer = { phone: newCustomerPhone(), name: 'Marta' }

  await test.step('a cliente paga com cartão e a loja ainda não aceitou', async () => {
    await addReadyProductFromMenu(page, testInfo, PRODUCT)
    await checkoutSigningInByCode(page, testInfo, customer)
    await placePickupTodayPayingByCard(page, testInfo)
  })

  await test.step('cancela no acompanhamento, e o diálogo diz antes que nada será cobrado', async () => {
    await cancelsOnTracking(page, testInfo, /A reserva no seu cartão será desfeita, e nada será cobrado\./)
  })

  await test.step('o acompanhamento diz que a reserva foi desfeita', async () => {
    await expect(page.locator('[data-cancellation-money]')).toContainText(
      /A reserva no seu cartão foi desfeita, e nada foi cobrado\./,
      { timeout: 60_000 }
    )
    await capture(page, testInfo, 'reserva-desfeita')
  })
})

test('J6-B: cancela depois do aceite e antes do preparo, e o valor volta ao cartão', async ({ page, browser }, testInfo) => {
  test.setTimeout(300_000)
  const customer = { phone: newCustomerPhone(), name: 'Celina' }

  const gestorContext = await browser.newContext({ baseURL: stack.gestor, viewport: gestorViewport, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' })
  const gestor = await gestorContext.newPage()
  try {
    await test.step('a operadora abre o Gestor', async () => {
      await acknowledgeOtherOrdersAlarms(gestor)
      await managerSignsIn(gestor)
    })

    const ref = await test.step('a cliente paga com cartão', async () => {
      await addReadyProductFromMenu(page, testInfo, PRODUCT)
      await checkoutSigningInByCode(page, testInfo, customer)
      return await placePickupTodayPayingByCard(page, testInfo)
    })

    await test.step('a operadora aceita: o aceite captura a cobrança', async () => {
      await acceptsNewOrder(gestor, testInfo, ref)
    })
  } finally {
    await gestorContext.close()
  }

  await test.step('o acompanhamento mostra o aceite', async () => {
    await expect(page.getByRole('tabpanel', { name: 'Histórico' }).getByText(/^Aceito/).first()).toBeVisible({ timeout: 60_000 })
  })

  await test.step('cancela antes do preparo, e o diálogo diz que o valor volta', async () => {
    // A frase exata do diálogo depende do momento do dinheiro; o que importa é que ela
    // fala do cartão e do valor, não de "nada cobrado" (que seria falso depois da captura).
    await cancelsOnTracking(page, testInfo, /cart[ãa]o/i)
    await expect(page.getByText(/nada (será|foi) cobrado/)).toHaveCount(0)
  })

  await test.step('o acompanhamento diz que o valor foi estornado no cartão', async () => {
    await expect(page.locator('[data-cancellation-money]')).toContainText(
      /Estornamos os R\$\s*\d+,\d{2} no seu cartão\. O valor volta na fatura no prazo do seu banco\./,
      { timeout: 120_000 }
    )
    await capture(page, testInfo, 'estornado')
  })
})
