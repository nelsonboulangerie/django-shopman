import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test'
import { addReadyProductFromMenu, checkoutSigningInByCode } from './support/customer'
import { capture, newCustomerPhone, settled } from './support/stack'

// J15 · Endereço fora da área, taxa por distância e a troca por retirada (#2569, item 4).
//
// Papel: a cliente nova, que quer receber em casa. Ela digita o endereço pelo CEP, e a loja
// responde com a taxa da faixa de distância em que o endereço cai; num endereço longe
// demais, a loja recusa a entrega e oferece a retirada, e a troca leva o pedido adiante.
//
// A taxa é por DISTÂNCIA da loja (faixas do seed `--profile qa`: até 3 km R$ 5,00, até 6 km
// R$ 8,00, até 10 km R$ 12,00, além disso fora da área). O endereço digitado chega ao
// servidor sem coordenada, e o servidor o geocodifica pelo texto. A pilha não tem chave de
// mapas: quem responde o geocoding são os mapas FALSOS da pilha
// (shopman/shop/tests/e2e/fake_maps.py), com uma tabela fixa de endereços cujas coordenadas
// caem cada uma numa faixa. O ViaCEP, que o NAVEGADOR consulta ao digitar o CEP, é desviado
// para o mesmo fake: a jornada não fala com serviço de fora.
//
// O seed cobra R$ 25,00 de mínimo só na entrega: dois Croissants (R$ 26,00) passam, e a
// recusa que a jornada vê é a da área, não a do mínimo.
//
// Nenhum estado nasce por API, Admin ou banco: a cliente põe na sacola, entra pelo código
// que chegou e digita o endereço.
const PRODUCT = 'Croissant' // pronto agora no seed `--profile qa`
const MAPS = (process.env.JOURNEY_MAPS_URL || `http://127.0.0.1:${process.env.JOURNEYS_MAPS_PORT || '12192'}`).replace(/\/$/, '')

interface TableAddress { cep: string, route: string, number: string, neighborhood: string }
// A tabela do fake_maps.py (as distâncias são as da loja do seed).
const NEAR: TableAddress = { cep: '86020-120', route: 'Rua Pernambuco', number: '1000', neighborhood: 'Centro' } // 2,5 km
const FAR: TableAddress = { cep: '86082-000', route: 'Avenida Saul Elkind', number: '2000', neighborhood: 'Lago Parque' } // 7,2 km
const OUTSIDE: TableAddress = { cep: '86118-000', route: 'Estrada do Limoeiro', number: '10', neighborhood: 'Irerê' } // 14,8 km

/** O ViaCEP que o navegador consulta ao digitar o CEP, desviado para os mapas falsos. */
async function viaCepFromFakeMaps (page: Page) {
  await page.context().route(/^https:\/\/viacep\.com\.br\/ws\/\d{8}\/json\/?$/, async (route) => {
    const cep = new URL(route.request().url()).pathname.split('/')[2]
    const response = await route.fetch({ url: `${MAPS}/ws/${cep}/json/` })
    await route.fulfill({ response })
  })
}

/** Da sacola com um Croissant, põe o segundo (o mínimo da entrega) e entra pelo código. */
async function twoCroissantsAndSignsIn (page: Page, testInfo: TestInfo) {
  await addReadyProductFromMenu(page, testInfo, PRODUCT)
  const quantity = page.getByRole('group', { name: `Quantidade de ${PRODUCT}` })
  await quantity.getByRole('button', { name: /Adicionar|Aumentar|Mais/i }).first().click()
  await expect(quantity).toContainText('2')
  await checkoutSigningInByCode(page, testInfo, { phone: newCustomerPhone(), name: 'Lúcia' })
  await page.getByRole('radio', { name: /^Entrega/ }).click()
  await expect(page.locator('[data-checkout-delivery-minimum]')).toHaveCount(0)
}

/** O passo "Endereço": abre o formulário (novo, manual) e digita o CEP primeiro; o CEP
 *  preenche rua, bairro, cidade e UF, e ela completa o número e confirma. */
async function typesAddressByCep (page: Page, address: TableAddress) {
  const step = page.locator("[data-checkout-step='address']")
  await expect(step.locator('[data-address-picker]')).toBeVisible()
  const form = step.locator('[data-address-form-card]')
  if (!(await form.isVisible().catch(() => false))) {
    const fresh = step.locator('[data-address-new]')
    if (await fresh.first().isVisible().catch(() => false)) await fresh.first().click()
    await step.locator('[data-address-manual]').click()
  }
  // Trocando de endereço, o formulário volta com o anterior: ela apaga e digita o novo.
  for (const field of ['#address-route', '#address-number', '#address-neighborhood']) await step.locator(field).fill('')
  const cep = step.locator('#address-cep')
  await cep.fill('')
  await cep.pressSequentially(address.cep.replace('-', ''))
  // O CEP preencheu o resto (o ViaCEP, aqui o fake): a rua e o bairro dele.
  await expect(step.locator('#address-route')).toHaveValue(address.route)
  await expect(step.locator('#address-neighborhood')).toHaveValue(address.neighborhood)
  await expect(step.locator('#address-city')).toHaveValue('Londrina')
  await step.locator('#address-number').fill(address.number)
  await step.locator('[data-address-confirm]').click()
}

/** Espera as transições pararem: a captura mostra a tela, não o meio da animação. */
async function untilStill (page: Page) {
  await page.waitForFunction(() => document.getAnimations()
    .filter(a => a.effect?.getTiming().iterations !== Infinity)
    .every(a => a.playState !== 'running'))
}

function isPhoneProject (testInfo: TestInfo): boolean {
  return (testInfo.project.use.viewport?.width ?? 0) < 768
}

/** O resumo do pedido: no celular, a folha que a linha do total abre; no computador, o
 *  resumo ao lado, sempre aberto. Lê, captura e fecha o que abriu. */
async function readsSummary (page: Page, testInfo: TestInfo, name: string, check: (summary: Locator) => Promise<void>) {
  if (!isPhoneProject(testInfo)) {
    const aside = page.locator('aside').filter({ hasText: 'Seu pedido' })
    await expect(aside).toBeVisible()
    await check(aside)
    await capture(page, testInfo, name)
    return
  }
  await page.getByRole('button', { name: 'Ver o resumo do pedido' }).click()
  const receipt = page.getByRole('dialog', { name: 'Seu pedido' })
  await expect(receipt).toBeVisible()
  await check(receipt)
  // A folha termina de subir antes da captura.
  await untilStill(page)
  await capture(page, testInfo, name)
  await page.keyboard.press('Escape')
  await expect(receipt).toBeHidden()
}

/** O resumo do pedido diz a taxa da entrega e a distância medida. */
async function summaryShowsDeliveryFee (page: Page, testInfo: TestInfo, fee: string, km: string, name: string) {
  await readsSummary(page, testInfo, name, async (summary) => {
    // "Entrega · 2,5 km" e, na mesma linha, a taxa da faixa.
    await expect(summary).toContainText(new RegExp(`Entrega · ${km}\\s*R\\$\\s*${fee}`))
  })
}

/** Volta ao passo do endereço pelo cabeçalho dele, para trocar o endereço. */
async function reopensAddress (page: Page) {
  const step = page.locator("[data-checkout-step='address']")
  await step.getByRole('button', { name: 'Editar', exact: true }).click()
  await expect(step.locator('[data-address-picker]')).toBeVisible()
}

test('J15: a taxa é a da faixa de distância; longe demais, a loja oferece a retirada', async ({ page }, testInfo) => {
  await viaCepFromFakeMaps(page)

  await test.step('a cliente põe dois Croissants na sacola, entra e escolhe entrega', async () => {
    await twoCroissantsAndSignsIn(page, testInfo)
  })

  await test.step('um endereço a 2,5 km: a loja entrega, com a taxa da primeira faixa', async () => {
    await typesAddressByCep(page, NEAR)
    // O endereço coberto leva ao passo seguinte; o resumo traz a taxa e a distância.
    await expect(page.locator("[data-checkout-step='when']")).toBeVisible()
    await summaryShowsDeliveryFee(page, testInfo, '5,00', '2,5 km', 'taxa-da-primeira-faixa')
  })

  await test.step('um endereço a 7,2 km: a taxa muda para a da faixa dele', async () => {
    await reopensAddress(page)
    await typesAddressByCep(page, FAR)
    await expect(page.locator("[data-checkout-step='when']")).toBeVisible()
    await summaryShowsDeliveryFee(page, testInfo, '12,00', '7,2 km', 'taxa-da-terceira-faixa')
  })

  await test.step('um endereço a 14,8 km: a loja recusa a entrega e oferece a retirada', async () => {
    await reopensAddress(page)
    await typesAddressByCep(page, OUTSIDE)
    const refusal = page.locator('[data-checkout-pickup-swap]')
    await expect(refusal).toBeVisible()
    await expect(refusal).toContainText('Ainda não entregamos nesse endereço')
    await expect(refusal).toContainText('Mas você pode retirar na loja quando quiser.')
    // A loja leva a página até a recusa, com o gesto que resolve à vista (beta SMS-05). A
    // rolagem é suave: a captura espera o botão inteiro na tela.
    await expect(refusal.getByRole('button', { name: 'Mudar para retirada' })).toBeInViewport({ ratio: 1 })
    // Achado da J15: a página para com o aviso sob o cabeçalho fixo, e o título e a frase
    // ("Ainda não entregamos…", "Mas você pode retirar…") ficam escondidos; só o botão
    // aparece (375 e 1366 px). A jornada afirma o gesto à vista, não a frase.
    testInfo.annotations.push({
      type: 'achado',
      description: 'a recusa de área para sob o cabeçalho fixo: título e frase escondidos, só o botão à vista'
    })
    // O passo não avança, e nenhuma taxa entra no total.
    await expect(page.locator('[data-checkout-zone-ok]')).toHaveCount(0)
    await capture(page, testInfo, 'fora-da-area')
  })

  await test.step('a cliente troca para retirada, e o pedido segue sem taxa de entrega', async () => {
    await page.locator('[data-checkout-pickup-swap]').getByRole('button', { name: 'Mudar para retirada' }).click()
    await expect(page.getByRole('radio', { name: /^Retirada/ })).toBeChecked()
    await expect(page.locator('[data-checkout-pickup-swap]')).toHaveCount(0)
    await expect(page.getByText('Horário da retirada')).toBeVisible()
    await settled(page)
    await readsSummary(page, testInfo, 'trocou-para-retirada', async (summary) => {
      await expect(summary).toContainText(`2× ${PRODUCT}`)
      // Nenhuma linha de entrega no total: nem a taxa, nem a distância.
      await expect(summary).not.toContainText(/Entrega\s*(·|R\$)/)
    })
  })
})
