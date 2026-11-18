import { expect, type Locator, type Page, type TestInfo } from '@playwright/test'
import { capture, cast, settled } from './stack'

// A operadora no Gestor: entra pela tela com o usuário e a senha dela e aceita o pedido
// novo no quadro. É o único papel de operador das jornadas da loja; o resto do Gestor é
// da suíte do próprio Gestor (surfaces/orders-nuxt/tests/operator).

/** A Gerente entra com usuário e senha. Um cookie de sessão velho pode devolver
 *  "Sua sessão terminou" uma vez: aí ela entra de novo, como faria. */
export async function managerSignsIn (page: Page): Promise<void> {
  await page.goto('/')
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await settled(page)
    const user = page.getByRole('textbox', { name: 'Usuário' })
    await expect(user).toBeVisible()
    await user.click()
    await user.pressSequentially(cast.manager.username)
    const password = page.getByRole('textbox', { name: 'Senha' })
    await password.click()
    await password.pressSequentially(cast.manager.password)
    await page.getByRole('button', { name: 'Entrar', exact: true }).click()
    await expect(page.getByRole('dialog', { name: 'Entre para operar' })).toBeHidden({ timeout: 30_000 })
    await settled(page)
    if (!(await page.getByText('Sua sessão terminou').first().isVisible().catch(() => false))) return
  }
  throw new Error('A Gerente não conseguiu entrar com a senha de dev.')
}

const alarms = new WeakMap<Page, Locator>()

/** O alarme "Pedido novo sem aceite" de OUTRO pedido (o seed, uma execução anterior que
 *  parou no meio) cobre a tela inteira e pode subir a qualquer momento. A operadora dá
 *  "Visto" nele, como faria; o do pedido da jornada fica intocado. Chame de novo com o
 *  código quando o pedido da jornada nascer. */
export async function acknowledgeOtherOrdersAlarms (page: Page, ownRef?: string): Promise<void> {
  const previous = alarms.get(page)
  if (previous) await page.removeLocatorHandler(previous)
  const alarm = page.getByRole('dialog').filter({ has: page.getByRole('heading', { name: 'Pedido novo sem aceite' }) })
  const foreign = ownRef ? alarm.filter({ hasNotText: ownRef }) : alarm
  alarms.set(page, foreign)
  await page.addLocatorHandler(foreign, async (dialog) => {
    await dialog.getByRole('button', { name: 'Visto', exact: true }).click()
  })
}

/** O cartão do pedido no quadro: o `article` que leva ao detalhe dele. */
export function orderCard (page: Page, ref: string): Locator {
  return page.getByRole('article').filter({ has: page.getByRole('link', { name: `Abrir pedido ${ref}`, exact: true }) })
}

/** O pedido chega sozinho ao quadro e a operadora toca em Aceitar: no cartão, ou no
 *  alarme do próprio pedido, se ele já cobriu a tela. */
export async function acceptsNewOrder (page: Page, testInfo: TestInfo, ref: string): Promise<void> {
  await acknowledgeOtherOrdersAlarms(page, ref)
  const card = orderCard(page, ref)
  await expect(card).toBeVisible({ timeout: 60_000 })
  await capture(page, testInfo, 'gestor-novo')
  const accept = card.getByRole('button', { name: 'Aceitar', exact: true })
  const alarm = page.getByRole('dialog').filter({ hasText: ref })
  if (await alarm.isVisible().catch(() => false)) {
    await alarm.getByRole('button', { name: 'Aceitar', exact: true }).click()
  } else {
    await expect(accept).toBeEnabled({ timeout: 60_000 })
    await accept.click()
  }
  await expect(accept).toHaveCount(0, { timeout: 60_000 })
  await capture(page, testInfo, 'gestor-aceito')
}
