import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test'
import { capture, inboxMark, newCustomerPhone, readLoginCode, settled, withInbox } from './support/stack'

// J11 · A conta da cliente (#2569, item 7): endereços, favoritos, preferências, segurança
// e exclusão, percorridos pela tela da loja.
//
// Papéis: a cliente que volta (do seed `--profile qa`), que entra com o código que chegou
// por SMS e cuida da própria conta; e uma cliente NOVA, criada aqui mesmo, que exclui a
// conta. A exclusão é definitiva: nunca se faz com uma cliente do seed, para não tirar de
// outra jornada quem ela espera encontrar.
//
// O que a cliente de volta muda, ela desfaz (o endereço novo sai, o padrão volta para a
// Casa, o favorito sai, a preferência volta ao que era): a conta dela termina como começou.
// Nenhum estado nasce por API, Admin ou banco.
//
// Cada projeto usa uma cliente diferente: o mesmo telefone nos dois cairia na espera do
// reenvio do código.
// `home` é a rua da Casa, o endereço padrão dela no seed.
const RETURNING: Record<string, { phone: string, name: string, home: string }> = {
  'cliente-375': { phone: '43991111111', name: 'Maria', home: 'Rua Belo Horizonte, 540' }, // CLI-001
  'cliente-1366': { phone: '43995555555', name: 'Ana', home: 'Rua Santos, 450' } // CLI-005
}
const PRODUCT = 'Croissant' // pronto agora no seed `--profile qa`
const NEW_ADDRESS = {
  cep: '86010190',
  route: 'Rua Quintino Bocaiúva',
  number: '1500',
  complement: 'Casa 2',
  neighborhood: 'Centro',
  city: 'Londrina',
  state: 'PR',
  label: 'Academia'
}

function returningCustomer (testInfo: TestInfo) {
  const who = RETURNING[testInfo.project.name]
  if (!who) throw new Error(`projeto sem cliente da J11: ${testInfo.project.name}`)
  return who
}

/** A cliente abre a Conta, a loja pede para entrar, e ela entra com o código do SMS. */
async function opensAccountSigningInByCode (page: Page, testInfo: TestInfo, phone: string): Promise<void> {
  await page.goto('/conta')
  await expect(page).toHaveURL(/\/entrar/)
  await settled(page)
  await page.getByRole('button', { name: 'Prefere receber um código por SMS?' }).click()
  const phoneField = page.getByRole('textbox', { name: 'Telefone', exact: true })
  await phoneField.click()
  await phoneField.pressSequentially(phone)
  const code = await withInbox(async () => {
    const mark = inboxMark()
    await page.getByRole('button', { name: 'Receber por SMS' }).click()
    return await readLoginCode(mark)
  })
  await page.getByRole('textbox', { name: 'Dígito 1 de 6' }).click()
  await page.keyboard.type(code)
  await capture(page, testInfo, 'codigo')
}

/** Da Conta, abre uma seção pelo cartão dela ("Endereços", "Favoritos"...). */
async function opensAccountSection (page: Page, section: RegExp, heading: string): Promise<void> {
  await page.goto('/conta')
  await settled(page)
  await page.getByRole('navigation', { name: 'Seções da conta' }).getByRole('link', { name: section }).click()
  await settled(page)
  await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible()
}

function savedCount (n: number): string {
  return n === 1 ? '1 endereço salvo' : `${n} endereços salvos`
}

/** O cartão de um endereço salvo, achado pela rua, que é o que a cliente lê. */
function addressCard (page: Page, street: string): Locator {
  return page.getByRole('listitem').filter({ hasText: street })
}

test('J11: a cliente que volta cuida da conta: endereço, favorito, preferência e segurança', async ({ page }, testInfo) => {
  const customer = returningCustomer(testInfo)

  await test.step('entra com o código e a Conta a chama pelo nome', async () => {
    await opensAccountSigningInByCode(page, testInfo, customer.phone)
    await expect(page).toHaveURL(/\/conta$/)
    await settled(page)
    await expect(page.getByRole('heading', { level: 1 })).toContainText(customer.name)
    await expect(page.getByRole('navigation', { name: 'Seções da conta' })).toBeVisible()
    await capture(page, testInfo, 'conta')
  })

  await test.step('endereços: cadastra um novo à mão, faz dele o padrão e depois o remove', async () => {
    await opensAccountSection(page, /^Endereços/, 'Endereços')
    const countLine = page.getByText(/^\d+ endereços? salvos?$/)
    await expect(countLine).toBeVisible()
    const before = Number((await countLine.textContent())!.match(/\d+/)![0])
    // A Casa é o padrão da cliente do seed.
    await expect(addressCard(page, customer.home).getByText('Padrão', { exact: true })).toBeVisible()
    await capture(page, testInfo, 'enderecos')

    await page.getByRole('button', { name: 'Adicionar endereço' }).first().click()
    const sheet = page.getByRole('dialog', { name: 'Adicionar endereço' })
    await expect(sheet).toBeVisible()
    // Sem chave do Google na pilha, o caminho é o formulário.
    await sheet.getByRole('button', { name: 'Preencher manualmente' }).click()
    const cep = sheet.getByRole('textbox', { name: 'CEP' })
    await cep.click()
    await cep.pressSequentially(NEW_ADDRESS.cep)
    // O CEP pode preencher a rua e a cidade; ela confere e escreve o que é dela.
    await expect(sheet.getByText('Buscando o endereço deste CEP…')).toBeHidden()
    await sheet.getByRole('textbox', { name: 'Rua' }).fill(NEW_ADDRESS.route)
    await sheet.getByRole('textbox', { name: 'Número' }).fill(NEW_ADDRESS.number)
    await sheet.getByRole('textbox', { name: 'Complemento' }).fill(NEW_ADDRESS.complement)
    await sheet.getByRole('textbox', { name: 'Bairro' }).fill(NEW_ADDRESS.neighborhood)
    await sheet.getByRole('textbox', { name: 'Cidade' }).fill(NEW_ADDRESS.city)
    await sheet.getByRole('combobox', { name: 'UF' }).click()
    await page.getByRole('option', { name: NEW_ADDRESS.state, exact: true }).click()
    await capture(page, testInfo, 'endereco-formulario')
    await sheet.getByRole('button', { name: 'Salvar endereço' }).click()

    // Salvo, a loja pergunta como chamar o endereço.
    const labelSheet = page.getByRole('dialog', { name: 'Endereço salvo' })
    await expect(labelSheet).toBeVisible()
    await expect(labelSheet.getByText('Como você quer chamar este endereço?')).toBeVisible()
    await labelSheet.getByRole('button', { name: 'Outro…' }).click()
    await labelSheet.getByRole('textbox', { name: 'Nome da etiqueta' }).fill(NEW_ADDRESS.label)
    await labelSheet.getByRole('button', { name: 'Salvar', exact: true }).click()
    await expect(labelSheet).toBeHidden()
    await expect(sheet).toBeHidden()

    const created = addressCard(page, NEW_ADDRESS.route)
    await expect(created).toContainText(NEW_ADDRESS.label)
    await expect(created).toContainText(`${NEW_ADDRESS.route}, ${NEW_ADDRESS.number}, ${NEW_ADDRESS.complement}`)
    await expect(created).toContainText(`${NEW_ADDRESS.neighborhood} · ${NEW_ADDRESS.city}/${NEW_ADDRESS.state}`)
    await expect(page.getByText(savedCount(before + 1), { exact: true })).toBeVisible()
    await capture(page, testInfo, 'endereco-novo')

    // Faz dele o padrão: o selo muda de endereço e continua lá depois de recarregar.
    await created.getByRole('button', { name: 'Definir padrão' }).click()
    await expect(created.getByText('Padrão', { exact: true })).toBeVisible()
    await expect(addressCard(page, customer.home).getByText('Padrão', { exact: true })).toHaveCount(0)
    await page.reload()
    await settled(page)
    await expect(addressCard(page, NEW_ADDRESS.route).getByText('Padrão', { exact: true })).toBeVisible()
    await capture(page, testInfo, 'endereco-padrao')

    // Desfaz: a Casa volta a ser o padrão e o endereço novo sai, com confirmação.
    await addressCard(page, customer.home).getByRole('button', { name: 'Definir padrão' }).click()
    await expect(addressCard(page, customer.home).getByText('Padrão', { exact: true })).toBeVisible()
    await addressCard(page, NEW_ADDRESS.route).getByRole('button', { name: 'Remover' }).click()
    const confirm = page.getByRole('alertdialog', { name: 'Remover endereço?' })
    await expect(confirm).toBeVisible()
    await expect(confirm).toContainText(NEW_ADDRESS.route)
    await capture(page, testInfo, 'endereco-remover')
    await confirm.getByRole('button', { name: 'Remover', exact: true }).click()
    await expect(confirm).toBeHidden()
    await expect(addressCard(page, NEW_ADDRESS.route)).toHaveCount(0)
    await expect(page.getByText(savedCount(before), { exact: true })).toBeVisible()
  })

  await test.step('favoritos: salva o produto pelo coração, o encontra na conta e o tira', async () => {
    await page.goto('/menu')
    await settled(page)
    await page.getByRole('link', { name: PRODUCT }).first().click()
    await expect(page).toHaveURL(/\/produto\//)
    await settled(page)
    await expect(page.getByRole('heading', { name: PRODUCT, level: 1 })).toBeVisible()
    await page.getByRole('button', { name: `Salvar ${PRODUCT} nos favoritos` }).click()
    const saved = page.getByRole('button', { name: `Remover ${PRODUCT} dos favoritos` })
    await expect(saved).toHaveAttribute('aria-pressed', 'true')
    await expect(saved).toBeEnabled()
    await capture(page, testInfo, 'favorito-salvo')

    await opensAccountSection(page, /^Favoritos/, 'Favoritos')
    await expect(page.getByText('1 item salvo', { exact: true })).toBeVisible()
    await expect(page.getByRole('main').getByRole('link', { name: new RegExp(PRODUCT) }).first()).toBeVisible()
    await capture(page, testInfo, 'favoritos')

    // Tira pelo próprio produto, aberto da lista de favoritos.
    await page.getByRole('main').getByRole('link', { name: new RegExp(PRODUCT) }).first().click()
    await expect(page).toHaveURL(/\/produto\//)
    await settled(page)
    await page.getByRole('button', { name: `Remover ${PRODUCT} dos favoritos` }).click()
    const unsaved = page.getByRole('button', { name: `Salvar ${PRODUCT} nos favoritos` })
    await expect(unsaved).toHaveAttribute('aria-pressed', 'false')
    await expect(unsaved).toBeEnabled()

    await opensAccountSection(page, /^Favoritos/, 'Favoritos')
    await expect(page.getByText('0 itens salvos', { exact: true })).toBeVisible()
    await expect(page.getByText('Você ainda não salvou favoritos')).toBeVisible()
    await capture(page, testInfo, 'favoritos-vazio')
  })

  await test.step('preferências: muda o aviso por SMS e a escolha continua depois de recarregar', async () => {
    await opensAccountSection(page, /^Preferências/, 'Preferências')
    await expect(page.getByText('Notificações', { exact: true })).toBeVisible()
    const sms = page.getByRole('switch', { name: 'SMS', exact: true })
    await expect(sms).toBeEnabled()
    const wasOn = (await sms.getAttribute('aria-checked')) === 'true'

    await sms.click()
    await expect(sms).toHaveAttribute('aria-checked', String(!wasOn))
    await expect(sms).toBeEnabled()
    await page.reload()
    await settled(page)
    await expect(page.getByRole('switch', { name: 'SMS', exact: true })).toHaveAttribute('aria-checked', String(!wasOn))
    await capture(page, testInfo, 'preferencia-mudada')

    // Desfaz: volta ao que era, e também fica.
    await page.getByRole('switch', { name: 'SMS', exact: true }).click()
    await expect(page.getByRole('switch', { name: 'SMS', exact: true })).toHaveAttribute('aria-checked', String(wasOn))
    await expect(page.getByRole('switch', { name: 'SMS', exact: true })).toBeEnabled()
    await page.reload()
    await settled(page)
    await expect(page.getByRole('switch', { name: 'SMS', exact: true })).toHaveAttribute('aria-checked', String(wasOn))
  })

  await test.step('segurança: vê o número dela, este acesso e este aparelho', async () => {
    await opensAccountSection(page, /^Segurança e dados/, 'Segurança e dados')
    await expect(page.getByRole('heading', { name: 'Seu número' })).toBeVisible()
    await expect(page.getByText(/\(43\) 9\d{4}-\d{4}/).first()).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Acessos recentes' })).toBeVisible()
    await expect(page.getByText('Este acesso', { exact: true })).toBeVisible()
    // Ela entrou deixando "Salvar este aparelho?" ligado (o padrão do login).
    await expect(page.getByRole('heading', { name: 'Aparelhos confiáveis' })).toBeVisible()
    await expect(page.getByText('Este aparelho', { exact: true })).toBeVisible()
    await capture(page, testInfo, 'seguranca')
    // Só olha: "Encerrar outros acessos" e "Remover" ficam como estão.
  })
})

test('J11: a cliente nova exclui a própria conta e sai da loja', async ({ page }, testInfo) => {
  const customer = { phone: newCustomerPhone(), name: 'Beatriz' }

  await test.step('cria a conta entrando com o código e dizendo o nome', async () => {
    await opensAccountSigningInByCode(page, testInfo, customer.phone)
    const name = page.getByRole('textbox', { name: 'Nome', exact: true })
    await expect(name).toBeVisible()
    await name.pressSequentially(customer.name)
    await page.getByRole('button', { name: 'Continuar', exact: true }).click()
    await expect(page).toHaveURL(/\/conta$/)
    await settled(page)
    await expect(page.getByRole('heading', { level: 1 })).toContainText(customer.name)
    await capture(page, testInfo, 'conta-nova')
  })

  await test.step('pede a exclusão, lê o efeito e confirma que entendeu', async () => {
    await opensAccountSection(page, /^Segurança e dados/, 'Segurança e dados')
    await expect(page.getByRole('heading', { name: 'Dados e privacidade' })).toBeVisible()
    await page.getByRole('button', { name: 'Excluir minha conta' }).click()
    const dialog = page.getByRole('alertdialog', { name: 'Excluir sua conta?' })
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('Apagamos seu nome, telefone, e-mail e endereços')
    await expect(dialog).toContainText('você sai da loja neste aparelho')
    // Sem marcar que entendeu, não há como seguir.
    await expect(dialog.getByRole('button', { name: 'Continuar' })).toBeDisabled()
    await dialog.getByRole('checkbox', { name: 'Entendi o efeito desta ação' }).click()
    await expect(dialog.getByRole('button', { name: 'Continuar' })).toBeEnabled()
    await capture(page, testInfo, 'excluir-dialogo')
  })

  await test.step('confirma a identidade com o código do SMS', async () => {
    const stepUp = page.getByRole('dialog', { name: 'Confirme sua identidade' })
    const wait = stepUp.locator('[data-step-up-wait]')
    const code = await withInbox(async () => {
      const mark = inboxMark()
      await page.getByRole('alertdialog', { name: 'Excluir sua conta?' }).getByRole('button', { name: 'Continuar' }).click()
      await expect(stepUp).toBeVisible()
      // O código do login acabou de ser usado. Na espera do reenvio (60 s desde ele), nada
      // foi enviado agora: a loja diz isso e quanto falta, sem erro e sem "Enviamos" (#3241).
      const outcome = await Promise.race([
        readLoginCode(mark).then(value => ({ code: value })),
        wait.waitFor({ timeout: 60_000 }).then(() => ({ code: '' }))
      ])
      if (outcome.code) {
        await expect(stepUp).toContainText('Enviamos um código para o seu telefone')
        return outcome.code
      }
      await expect(wait).toContainText(/^Um código foi enviado a este número há pouco\. Por segurança, o próximo pode ser pedido em \d+ segundos?\.$/)
      await expect(stepUp).not.toContainText('Enviamos um código')
      await expect(stepUp.getByText('Não foi possível confirmar')).toHaveCount(0)
      const send = stepUp.getByRole('button', { name: 'Enviar código', exact: true })
      await expect(send).toBeDisabled()
      await capture(page, testInfo, 'identidade-espera-do-reenvio')
      // A espera acaba: o botão liga, ela pede, e aí sim o código vai.
      await expect(send).toBeEnabled({ timeout: 70_000 })
      await send.click()
      await expect(stepUp).toContainText('Enviamos um código para o seu telefone')
      return await readLoginCode(mark)
    })
    await stepUp.getByRole('textbox', { name: 'Dígito 1 de 6' }).click()
    await page.keyboard.type(code)
    await capture(page, testInfo, 'identidade-codigo')
    await stepUp.getByRole('button', { name: 'Confirmar', exact: true }).click()
  })

  await test.step('a conta sai e ela volta à loja sem estar conectada', async () => {
    await expect.poll(() => new URL(page.url()).pathname, { timeout: 60_000 }).toBe('/')
    // O fim do gesto não é silêncio: a loja diz que excluiu e o que isso significou (#3242).
    await expect(page.getByText(/^Pronto, sua conta foi excluída\./).first()).toBeVisible()
    await settled(page)
    await capture(page, testInfo, 'excluida-inicio')
    // A Conta pede para entrar de novo: a sessão dela acabou junto com a conta.
    await page.goto('/conta')
    await expect(page).toHaveURL(/\/entrar/)
    await settled(page)
    await expect(page.getByRole('button', { name: 'Prefere receber um código por SMS?' })).toBeVisible()
    await capture(page, testInfo, 'excluida-entrar')
  })
})
