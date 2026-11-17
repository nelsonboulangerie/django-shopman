import { expect, type Page, type TestInfo } from '@playwright/test'
import { capture, inboxMark, readLoginCode, settled } from './stack'

// A cliente na loja: cardápio, produto, sacola, entrar com o código que chegou, finalizar e
// pagar. Os passos são os da pessoa; o código sai do arquivo do sender da pilha, que é onde
// ela leria o SMS.

export interface NewCustomer {
  phone: string
  name: string
}

/** No cardápio, abre o produto pelo nome e o põe na sacola pela página dele. */
export async function addReadyProductFromMenu (page: Page, testInfo: TestInfo, product: string): Promise<void> {
  await page.goto('/menu')
  await settled(page)
  await expect(page.getByText(/^Aberto/).first(), 'a loja da pilha precisa estar aberta agora (README: seed com a loja aberta)').toBeVisible()
  await capture(page, testInfo, 'cardapio')

  await page.getByRole('link', { name: product }).first().click()
  await expect(page).toHaveURL(/\/produto\//)
  await settled(page)
  await expect(page.getByRole('heading', { name: product, level: 1 })).toBeVisible()
  await page.getByRole('button', { name: /^Adicionar/ }).first().click()
  await expect(page.getByRole('link', { name: /^Sacola, 1 item/ }).first()).toBeVisible()
  await capture(page, testInfo, 'produto')

  await page.getByRole('link', { name: /^Sacola, 1 item/ }).first().click()
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
  const mark = inboxMark()
  await page.getByRole('button', { name: 'Receber por SMS' }).click()
  const code = await readLoginCode(mark)
  await page.getByRole('textbox', { name: 'Dígito 1 de 6' }).click()
  await page.keyboard.type(code)
  await capture(page, testInfo, 'codigo')

  // Cliente nova: a loja pergunta como chamar.
  const name = page.getByRole('textbox', { name: 'Nome', exact: true })
  await expect(name).toBeVisible()
  await name.pressSequentially(who.name)
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  await expect(page).toHaveURL(/\/finalizar/)
  await settled(page)
}

/** Finalizar, uma etapa por vez: retirada, hoje, o primeiro horário, Pix; revisar e enviar.
 *  Devolve o código do pedido, como a loja o mostra no endereço do acompanhamento. */
export async function placePickupTodayWithPix (page: Page, testInfo: TestInfo): Promise<string> {
  await page.getByRole('radio', { name: /^Retirada/ }).click()
  await page.getByRole('button', { name: 'Continuar', exact: true }).click()
  await expect(page.getByText('Horário da retirada')).toBeVisible()
  await page.getByRole('radio', { name: /^Hoje/ }).click().catch(() => undefined)
  await page.getByRole('radio', { name: /^\d{2}:\d{2} às \d{2}:\d{2}$/ }).first().click()
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

/** No acompanhamento, paga o Pix com o pagamento simulado da pilha. */
export async function paysPixOnTracking (page: Page, testInfo: TestInfo): Promise<void> {
  await capture(page, testInfo, 'pix')
  await page.getByRole('button', { name: 'Simular pagamento' }).click()
  await expect(page.getByText('Pagamento recebido').first()).toBeVisible({ timeout: 60_000 })
  await capture(page, testInfo, 'pago')
}
