import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { inboxMark, readLoginCode, withInbox } from '../../journeys/support/stack'
import { experience, expectServerVariant, hydrated, readShell, serverVariants } from './support/experience'

// Antes das jornadas: a cliente da comparação entra pelo código que chegou, como entraria
// no celular. É neste momento que o servidor decide a versão dela (a coorte é por
// customer_ref, D2: anônimo nunca entra em coorte); por isso as jornadas começam já
// logadas, e o passo é o mesmo nas duas versões.
//
// Um login só por rodada: o código por SMS tem limite por telefone (5 em 15 min), e sete
// jornadas com sete logins estourariam. A sessão vai para o arquivo que as jornadas usam.
test('a cliente entra pelo código, e o servidor decide a versão dela', async ({ page }) => {
  await page.goto('/entrar')
  await hydrated(page)
  await page.getByRole('button', { name: 'Prefere receber um código por SMS?' }).click()
  const phone = page.getByRole('textbox', { name: 'Telefone', exact: true })
  await phone.click()
  await phone.pressSequentially(experience.phone)
  const code = await withInbox(async () => {
    const mark = inboxMark()
    await page.getByRole('button', { name: 'Receber por SMS' }).click()
    return await readLoginCode(mark)
  })
  await page.getByRole('textbox', { name: 'Dígito 1 de 6' }).click()
  await page.keyboard.type(code)
  await expect(page).not.toHaveURL(/\/entrar/, { timeout: 60_000 })
  await hydrated(page)

  // A versão é a que o servidor decidiu; a rodada só confere que é a esperada.
  mkdirSync(experience.out, { recursive: true })
  writeFileSync(join(experience.out, 'rodada.json'), JSON.stringify({
    variant: experience.variant,
    serverVariants: await serverVariants(page),
    refs: experience.refs,
    customer: experience.customer,
    startedAt: new Date().toISOString(),
    shell: await readShell(page)
  }, null, 2))
  await expectServerVariant(page)
  await page.context().storageState({ path: join(experience.out, 'sessao.json') })
})
