import { expect, type Page } from '@playwright/test'
import { cast, settled } from './stack'

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
