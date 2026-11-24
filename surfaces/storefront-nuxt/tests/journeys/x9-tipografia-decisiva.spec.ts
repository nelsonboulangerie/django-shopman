import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { addReadyProductFromMenu, checkoutSigningInByCode, placePickupTodayWithPix } from './support/customer'
import { capture, newCustomerPhone, settled } from './support/stack'
import { auditTypographyInPage } from './support/typographyAudit.mjs'

// X9 e X11 (docs/reports/2026-11-23-etapa-ii-omnicanal-espec-e-plano.md, §6; OC-30): o que
// decide a compra se lê sem esforço, em todas as rotas essenciais da loja.
//
//   X9:  todo `[data-decisive]` (preço, disponibilidade, total, estado, erro) tem 14 px ou
//        mais e contraste AA contra o fundo de verdade, no tema claro e no escuro; todo
//        `.shop-reading` tem 16 px.
//   X11: com a fonte raiz a 200 %, nenhum decisivo nem ação some, sai da tela ou é cortado.
//
// A cliente nova percorre a loja como a J1 (cardápio, produto, sacola, entrar pelo código,
// finalizar, Pix, acompanhamento, conta) e, em cada parada, a página é medida no celular a
// 320, 375 e 390 px (projeto `cliente-375`) e no computador a 1366 px (`cliente-1366`).
// A medida é a mesma que a prévia do PR usa (support/typographyAudit.mjs).
const PRODUCT = 'Croissant' // pronto agora no seed `--profile qa`

function widthsOf (testInfo: TestInfo): number[] {
  return testInfo.project.name === 'cliente-375' ? [320, 375, 390] : [1366]
}

async function layoutSettled (page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  })
  // Trocar o tema anima as cores (transition-colors): medir no meio da transição dá um
  // contraste que a cliente nunca vê parado. Espera as transições finitas terminarem.
  await page.waitForFunction(() => document.getAnimations()
    .filter(a => a.effect?.getTiming().iterations !== Infinity)
    .every(a => a.playState !== 'running'), undefined, { timeout: 5_000 }).catch(() => undefined)
}

/** Mede a página nas larguras do projeto, com a fonte normal e a 200 %. */
async function expectReadable (page: Page, testInfo: TestInfo, route: string, opts: { decisive: boolean }): Promise<void> {
  const original = page.viewportSize()!
  // O resumo do finalizar e o acompanhamento chegam depois da hidratação: espera o primeiro
  // decisivo à vista, por elemento (a loja mantém SSE aberto e "networkidle" pode não vir).
  if (opts.decisive) {
    await expect.poll(() => page.locator('[data-decisive]:visible').count(), { message: `${route}: algum [data-decisive] à vista` }).toBeGreaterThan(0)
  }
  for (const width of widthsOf(testInfo)) {
    await page.setViewportSize({ width, height: original.height })
    // O contraste vale nos dois temas: a loja segue o tema do sistema da cliente.
    for (const colorScheme of ['light', 'dark'] as const) {
      await page.emulateMedia({ colorScheme })
      await expect(page.locator('html')).toHaveClass(new RegExp(`\\b${colorScheme}\\b`))
      await layoutSettled(page)
      // Trocar a largura pode remontar o bloco (o resumo do finalizar some e volta entre o
      // celular e o computador): espera os decisivos reaparecerem antes de medir.
      if (opts.decisive) {
        await expect.poll(async () => (await page.evaluate(auditTypographyInPage, {})).measured.length, { message: `${route} a ${width} px: algum [data-decisive] medido` }).toBeGreaterThan(0)
      }
      const normal = await page.evaluate(auditTypographyInPage, {})
      expect(normal.findings, `${route} a ${width} px no tema ${colorScheme}: decisivo abaixo de 14 px ou sem AA, corpo de leitura abaixo de 16 px, rolagem lateral`).toEqual([])
      if (opts.decisive) expect(normal.measured.length, `${route} a ${width} px: nenhum [data-decisive] à vista`).toBeGreaterThan(0)
      // Exceção de contraste só a declarada, com a issue que a tira: o selo âmbar da marca
      // (3,73:1 com letra branca), mantido por decisão do dono até o âmbar escurecer (#3523).
      expect(normal.exceptions.map(e => e.exception).filter(e => e !== 'ambar-da-marca-3523'), `${route} a ${width} px: exceção de contraste não declarada`).toEqual([])
      if (normal.exceptions.length) testInfo.annotations.push({ type: 'exceção de contraste (#3523)', description: `${route} ${width} px ${colorScheme}: ${[...new Set(normal.exceptions.map(e => `${e.text} ${e.contrast}:1`))].join(', ')}` })
    }
    await page.emulateMedia({ colorScheme: 'light' })

    await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
    await layoutSettled(page)
    const zoomed = await page.evaluate(auditTypographyInPage, { zoomed: true })
    await page.evaluate(() => { document.documentElement.style.fontSize = '' })
    expect(zoomed.findings, `${route} a ${width} px com a fonte a 200 %: decisivo ou ação sumiu, saiu da tela ou foi cortado`).toEqual([])
  }
  await page.setViewportSize(original)
  await layoutSettled(page)
}

test('X9 e X11: preço, disponibilidade, total, estado e erro se leem sem esforço nas rotas essenciais', async ({ page }, testInfo) => {
  await test.step('home, cardápio e produto, sem entrar', async () => {
    await page.goto('/')
    await settled(page)
    await expect(page.locator('[data-product-tile]').first()).toBeVisible()
    await expectReadable(page, testInfo, 'home', { decisive: true })

    await page.goto('/menu')
    await settled(page)
    await expect(page.locator('[data-product-list-item], [data-product-tile]').first()).toBeVisible()
    await expectReadable(page, testInfo, 'cardápio', { decisive: true })

    await page.getByRole('link', { name: PRODUCT }).first().click()
    await expect(page).toHaveURL(/\/produto\//)
    await settled(page)
    await expect(page.getByRole('heading', { name: PRODUCT, level: 1 })).toBeVisible()
    await expectReadable(page, testInfo, 'produto', { decisive: true })

    await page.goto('/entrar')
    await settled(page)
    await expectReadable(page, testInfo, 'entrar', { decisive: false })
  })

  await test.step('sacola, entrar e finalizar', async () => {
    await addReadyProductFromMenu(page, testInfo, PRODUCT)
    await expectReadable(page, testInfo, 'sacola', { decisive: true })
    await checkoutSigningInByCode(page, testInfo, { phone: newCustomerPhone(), name: 'Lúcia' })
    await expectReadable(page, testInfo, 'finalizar', { decisive: true })
  })

  await test.step('acompanhamento e conta', async () => {
    await placePickupTodayWithPix(page, testInfo)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expectReadable(page, testInfo, 'acompanhamento', { decisive: true })
    await capture(page, testInfo, 'acompanhamento')

    await page.goto('/conta')
    await settled(page)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expectReadable(page, testInfo, 'conta', { decisive: true })
  })
})
