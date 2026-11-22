import { expect, type Page, type TestInfo } from '@playwright/test'
import { capture, inboxMark, readLoginCode, settled, withInbox } from './stack'

// A cliente na loja: cardápio, produto, sacola, entrar com o código que chegou, finalizar e
// pagar. Os passos são os da pessoa; o código sai do arquivo do sender da pilha, que é onde
// ela leria o SMS.

export interface NewCustomer {
  phone: string
  /** Só a cliente nova diz o nome; a que volta (o seed, `--profile qa`) entra direto. */
  name?: string
}

/** O link da sacola: "Sacola, 1 item", na barra de baixo (celular) e no cabeçalho (desktop). */
function bagLink (page: Page) {
  return page.getByRole('link', { name: 'Sacola, 1 item', exact: true }).first()
}

/** No cardápio, abre o produto pelo nome e o põe na sacola pela página dele. */
export async function addReadyProductFromMenu (page: Page, testInfo: TestInfo, product: string): Promise<void> {
  await page.goto('/menu')
  await settled(page)
  // Aberta é "Aberto até 19h" ou, na última hora antes de fechar, "Últimos pedidos até 19h".
  await expect(page.getByText(/^(Aberto|Últimos pedidos)\b/).first(), 'a loja da pilha precisa estar aberta agora (README: seed com a loja aberta)').toBeVisible()
  await capture(page, testInfo, 'cardapio')

  await page.getByRole('link', { name: product }).first().click()
  await expect(page).toHaveURL(/\/produto\//)
  await settled(page)
  await expect(page.getByRole('heading', { name: product, level: 1 })).toBeVisible()
  // O "Adicionar" do produto da página (na barra fixa do celular ou ao lado do preço no
  // desktop); os de "Você também pode gostar" se chamam "Adicionar <outro produto>".
  await page.getByRole('button', { name: 'Adicionar', exact: true }).first().click()
  // Na sacola: o botão vira o seletor de quantidade, com 1.
  await expect(page.getByRole('group', { name: `Quantidade de ${product}` })).toContainText('1')
  await capture(page, testInfo, 'produto')

  await bagLink(page).click()
  await expect(page.getByRole('heading', { name: 'Sua sacola' })).toBeVisible()
  await expect(page.getByText(product).first()).toBeVisible()
  await capture(page, testInfo, 'sacola')
}

/** Da sacola, segue para finalizar; a loja pede para entrar e a cliente entra por código. */
export async function checkoutSigningInByCode (page: Page, testInfo: TestInfo, who: NewCustomer): Promise<void> {
  await page.getByRole('link', { name: 'Finalizar pedido' }).last().click()
  await expect(page).toHaveURL(/\/entrar/)
  await settled(page)
  await page.getByRole('button', { name: 'Prefere receber um código por SMS?' }).click()
  const phone = page.getByRole('textbox', { name: 'Telefone', exact: true })
  await phone.click()
  await phone.pressSequentially(who.phone)
  const code = await withInbox(async () => {
    const mark = inboxMark()
    await page.getByRole('button', { name: 'Receber por SMS' }).click()
    return await readLoginCode(mark)
  })
  await page.getByRole('textbox', { name: 'Dígito 1 de 6' }).click()
  await page.keyboard.type(code)
  await capture(page, testInfo, 'codigo')

  // Cliente nova: a loja pergunta como chamar. A que volta já tem nome.
  if (who.name) {
    const name = page.getByRole('textbox', { name: 'Nome', exact: true })
    await expect(name).toBeVisible()
    await name.pressSequentially(who.name)
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  }
  await expect(page).toHaveURL(/\/finalizar/)
  await settled(page)
}

/** Finalizar, uma etapa por vez: retirada, hoje, o primeiro horário (no formato da casa, "10h30 às 11h"), Pix; revisar e enviar.
 *  Devolve o código do pedido, como a loja o mostra no endereço do acompanhamento. */
export async function placePickupTodayWithPix (page: Page, testInfo: TestInfo): Promise<string> {
  await page.getByRole('radio', { name: /^Retirada/ }).click()
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  await expect(page.getByText('Horário da retirada')).toBeVisible()
  await page.getByRole('radio', { name: /^Hoje/ }).click().catch(() => undefined)
  await page.getByRole('radio', { name: /^\d{1,2}h(\d{2})? às \d{1,2}h(\d{2})?$/ }).first().click()
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  await page.getByRole('radio', { name: /^Pix/ }).click()
  await capture(page, testInfo, 'finalizar')
  await page.getByRole('button', { name: 'Revisar pedido' }).click()
  await expect(page.getByText(/Retirada · Hoje/).last()).toBeVisible()
  await capture(page, testInfo, 'revisar')
  await page.getByRole('button', { name: 'Enviar pedido' }).click()

  await expect(page).toHaveURL(/\/pedido\/[^/]+$/, { timeout: 60_000 })
  await settled(page)
  return decodeURIComponent(new URL(page.url()).pathname.split('/').pop()!)
}

/** Finalizar com CARTÃO: retirada, hoje, o primeiro horário, cartão; revisar e enviar. A
 *  loja passa pelo acompanhamento e leva sozinha à "página do Stripe" (o Stripe falso da
 *  pilha, `fake_stripe.py`); ela paga e volta ao acompanhamento, já com a autorização
 *  gravada (o fake entrega o webhook antes do redirect). Devolve o código do pedido. */
export async function placePickupTodayPayingByCard (page: Page, testInfo: TestInfo): Promise<string> {
  await page.getByRole('radio', { name: /^Retirada/ }).click()
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  await expect(page.getByText('Horário da retirada')).toBeVisible()
  await page.getByRole('radio', { name: /^Hoje/ }).click().catch(() => undefined)
  await page.getByRole('radio', { name: /^\d{1,2}h(\d{2})? às \d{1,2}h(\d{2})?$/ }).first().click()
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  await page.getByRole('radio', { name: /^Cartão/ }).click()
  await capture(page, testInfo, 'finalizar-cartao')
  await page.getByRole('button', { name: 'Revisar pedido' }).click()
  await expect(page.getByRole('heading', { name: 'Revise seu pedido' })).toBeVisible()
  await capture(page, testInfo, 'revisar-cartao')

  // A parada no acompanhamento antes do pagamento é curta: o código sai do caminho.
  const visited: string[] = []
  page.on('framenavigated', frame => { if (frame === page.mainFrame()) visited.push(frame.url()) })
  await page.getByRole('button', { name: 'Enviar pedido' }).click()
  await page.waitForURL(/\/pay\/cs_test_/, { timeout: 60_000 })
  const ref = visited.map(url => url.match(/\/pedido\/([^/?#]+)/)?.[1]).find(Boolean)
  expect(ref, `a loja deveria passar pelo acompanhamento antes do pagamento: ${visited.join(', ')}`).toBeTruthy()

  await expect(page.getByRole('heading', { name: /Checkout de teste/ })).toBeVisible()
  await capture(page, testInfo, 'stripe-falso')
  await page.getByRole('button', { name: 'Pagar' }).click()
  await page.waitForURL(new RegExp(`/pedido/${ref}(\\?.*)?$`), { timeout: 60_000 })
  await settled(page)
  await expect(page.getByText('Pagamento autorizado').first()).toBeVisible({ timeout: 30_000 })
  await capture(page, testInfo, 'cartao-autorizado')
  return decodeURIComponent(ref!)
}

/** No acompanhamento, cancela o pedido e confirma no diálogo, que diz do dinheiro antes. */
export async function cancelsOnTracking (page: Page, testInfo: TestInfo, moneyBefore: RegExp): Promise<void> {
  await page.getByRole('button', { name: 'Cancelar pedido', exact: true }).click()
  const dialog = page.getByRole('alertdialog')
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText(moneyBefore)
  await capture(page, testInfo, 'cancelar-dialogo')
  await dialog.getByRole('button', { name: 'Sim, cancelar' }).click()
  await expect(page.getByRole('tabpanel', { name: 'Histórico' }).getByText(/^Cancelado/).first()).toBeVisible({ timeout: 60_000 })
}

/** No acompanhamento, paga o Pix com o pagamento simulado da pilha. */
export async function paysPixOnTracking (page: Page, testInfo: TestInfo): Promise<void> {
  await capture(page, testInfo, 'pix')
  await page.getByRole('button', { name: 'Simular pagamento' }).click()
  await expect(page.getByText('Pagamento recebido').first()).toBeVisible({ timeout: 60_000 })
  // Pago e ainda sem aceite: a loja diz que está conferindo.
  await expect(page.getByText(/^Estamos conferindo a disponibilidade/).first()).toBeVisible()
  await capture(page, testInfo, 'pago')
}
