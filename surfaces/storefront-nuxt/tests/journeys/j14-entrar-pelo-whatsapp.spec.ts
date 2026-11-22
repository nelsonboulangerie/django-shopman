import { devices, expect, test, type APIRequestContext, type Browser, type BrowserContext, type Page, type TestInfo } from '@playwright/test'
import { addReadyProductFromMenu } from './support/customer'
import { capture, newCustomerPhone, settled, stack } from './support/stack'

// J14 · Entrar pelo WhatsApp (#2569, item 10).
//
// Papéis: a cliente nova, com um item na sacola, e o ManyChat, que recebe a mensagem que
// ela manda no WhatsApp. A cliente vai finalizar, a loja pede para entrar, e o caminho da
// frente é o WhatsApp: o painel diz por que, mostra três passos e tem UM botão. O toque
// abre o WhatsApp com a mensagem pronta, e a tela passa a esperar por ela.
//
// O WhatsApp de verdade não é aberto: o link `wa.me` é interceptado, e a mensagem pronta é
// lida do próprio link, como a cliente a veria no campo de texto. Quem a recebe é o
// ManyChat, e o papel dele é a única chamada que a jornada faz por conta própria: o mesmo
// POST que o External Request do fluxo faz ao Django (docs/guides/whatsapp-access-link.md),
// como o Stripe falso faz o papel do cartão. A pilha roda com DEBUG e sem
// ACCESS_LINK_API_KEY, então a ponte aceita a chamada sem chave.
//
// Onde a entrada acontece depende de onde o login começou (decisão do dono, 23/10;
// shopman/shop/services/access.py), e a loja decide pelo agente de usuário:
// - no CELULAR (375 px, agente de um Android), a resposta traz "Voltar à loja", e a entrada
//   acontece no navegador que esse botão abrir; a aba que esperava percebe sozinha;
// - no COMPUTADOR (1366 px), a resposta traz "Liberar o Chrome", e só o toque nesse botão,
//   no celular, solta a aba. A mensagem sozinha não deixa ninguém entrar.
//
// A resposta da casa sai de verdade, pelo adapter do ManyChat, e cai no ManyChat FALSO da
// pilha (shopman/shop/tests/e2e/fake_manychat.py, #3272), que a guarda. É dali que o
// celular da cliente (outro navegador, outro dispositivo) tira o link de cada botão:
// "Liberar o Chrome" solta a aba do computador, e "Encerrar acesso" (o "Não foi você?")
// desfaz a entrada que já aconteceu.
//
// Nenhum estado nasce por API, Admin ou banco além da mensagem que o ManyChat recebe.
const PRODUCT = 'Croissant' // pronto agora no seed `--profile qa`
const PHONE_USER_AGENT = devices['Pixel 7'].userAgent
// O Django da pilha (scripts/run_storefront_journeys.sh): é ali que o ManyChat bate.
const DJANGO = (process.env.JOURNEY_DJANGO_URL || `http://127.0.0.1:${process.env.JOURNEYS_DJANGO_PORT || '8090'}`).replace(/\/$/, '')
// O ManyChat falso da pilha, onde a resposta da casa fica guardada para a jornada ler.
const MANYCHAT = (process.env.JOURNEY_MANYCHAT_URL || `http://127.0.0.1:${process.env.JOURNEYS_MANYCHAT_PORT || '12191'}`).replace(/\/$/, '')
const STORE = stack.store

interface WhatsappContact {
  phone: string
  name: string
  subscriberId: string
}

function newContact (): WhatsappContact {
  const phone = newCustomerPhone()
  // O id do assinante no ManyChat é numérico e nunca se repete entre execuções.
  return { phone, name: 'Teresa', subscriberId: `9${phone}` }
}

/** Espera as transições pararem: a captura mostra a tela, não o meio da animação. O
 *  ícone que gira na espera é infinito de propósito e não conta. */
async function untilStill (page: Page) {
  await page.waitForFunction(() => document.getAnimations()
    .filter(a => a.effect?.getTiming().iterations !== Infinity)
    .every(a => a.playState !== 'running'))
}

function isPhoneProject (testInfo: TestInfo): boolean {
  return (testInfo.project.use.viewport?.width ?? 0) < 768
}

/** Da sacola, segue para finalizar e chega à porta de entrada, com o WhatsApp na frente. */
async function goesToSignInFromBag (page: Page, testInfo: TestInfo, replyButton: RegExp) {
  await page.getByRole('link', { name: 'Finalizar pedido' }).last().click()
  await expect(page).toHaveURL(/\/entrar\?next=%2Ffinalizar|\/entrar\?next=\/finalizar/)
  await settled(page)
  await expect(page.getByRole('heading', { name: 'Entre pelo WhatsApp', level: 1 })).toBeVisible()
  // A sacola segue com o item enquanto ela entra, e a página diz isso (#3271: ela lia
  // a sacola do shell em cache, vazio, e caía no neutro "Sem senha, rápido e seguro.").
  await expect(page.getByRole('link', { name: 'Sacola, 1 item', exact: true }).first()).toBeVisible()
  await expect(page.getByText('Sua sacola está guardada.')).toBeVisible()
  await expect(page.getByText('Sem senha, rápido e seguro.')).toHaveCount(0)

  const panel = page.locator('[data-login-whatsapp-open]')
  // O porquê vem antes dos passos.
  await expect(panel.locator('[data-login-whatsapp-why]')).toContainText('A mensagem pronta confirma que o número é seu.')
  const steps = panel.locator('[data-login-whatsapp-steps] li')
  await expect(steps).toHaveCount(3)
  await expect(steps.nth(0)).toContainText('Abrir o WhatsApp')
  // O terceiro passo chama o botão da resposta pelo nome que ele terá no WhatsApp.
  await expect(steps.nth(2)).toContainText(replyButton)
  // UM botão, e ele só vale quando o link da mensagem está pronto.
  const open = panel.getByRole('link', { name: 'Abrir o WhatsApp' })
  await expect(open).toHaveAttribute('href', /^https:\/\/wa\.me\/\d+\?text=/)
  await expect(panel.getByRole('link')).toHaveCount(1)
  await expect(panel.getByRole('button')).toHaveCount(0)
  // O SMS fica como alternativa discreta, fora do painel.
  await expect(page.getByRole('button', { name: 'Prefere receber um código por SMS?' })).toBeVisible()
  await untilStill(page)
  await capture(page, testInfo, 'entrar-pelo-whatsapp')
}

/** Toca em "Abrir o WhatsApp". O WhatsApp não abre de verdade: a mensagem pronta é lida do
 *  link, e a aba volta a ser a da loja. Devolve a mensagem. */
async function opensWhatsapp (page: Page, testInfo: TestInfo): Promise<string> {
  const opened: string[] = []
  await page.context().route(/^https:\/\/(wa\.me|api\.whatsapp\.com)\//, async (route) => {
    opened.push(route.request().url())
    await route.abort()
  })
  const panel = page.locator('[data-login-whatsapp-open]')
  const href = await panel.getByRole('link', { name: 'Abrir o WhatsApp' }).getAttribute('href')
  const popup = page.waitForEvent('popup')
  await panel.getByRole('link', { name: 'Abrir o WhatsApp' }).click()
  const whatsapp = await popup
  await expect.poll(() => opened.length, { message: 'o toque abriu o link do WhatsApp' }).toBeGreaterThan(0)
  expect(opened[0]).toBe(href)
  await whatsapp.close()
  await page.bringToFront()

  const message = new URL(opened[0]!).searchParams.get('text') ?? ''
  // Uma frase que a pessoa mandaria por conta própria, com a referência no fim.
  expect(message).toMatch(/^Olá! Quero entrar no site da .+ \(ref\. NB-\w+\)$/)

  // A tela espera a mensagem; o plano B (enviar à mão) só aparece agora.
  const waiting = page.locator('[data-login-whatsapp-waiting]')
  await expect(waiting).toBeVisible()
  await expect(waiting).toContainText('Mensagem enviada?')
  await expect(waiting.locator('[data-login-whatsapp-manual]')).toContainText(message)
  // A frase inteira cabe na tela, com a referência NB-… no fim: quebra a linha, nunca se
  // corta (#3271: o `truncate` deixava "Olá! Quero entrar n…").
  const shown = waiting.locator('[data-login-whatsapp-manual-message]')
  await expect(shown).toHaveText(message)
  expect(await shown.evaluate(el => el.scrollWidth <= el.clientWidth), 'a mensagem não transborda').toBe(true)
  await shown.scrollIntoViewIfNeeded()
  await untilStill(page)
  await capture(page, testInfo, 'plano-b-mensagem-inteira')
  await page.evaluate(() => window.scrollTo(0, 0))
  await untilStill(page)
  await capture(page, testInfo, 'esperando-a-mensagem')
  return message
}

/** "Já enviei. Conferir agora" antes de a mensagem chegar: a tela diz que conferiu. */
async function checksBeforeTheMessageArrives (page: Page, testInfo: TestInfo) {
  await page.getByRole('button', { name: 'Já enviei. Conferir agora' }).click()
  await expect(page.locator('[data-login-whatsapp-not-arrived]')).toBeVisible()
  await expect(page.locator('[data-login-whatsapp-not-arrived]')).toContainText('Conferimos agora e sua mensagem ainda não chegou.')
  await capture(page, testInfo, 'conferiu-e-ainda-nao-chegou')
}

interface AccessLinkCreated {
  access_url: string
  has_cart_context: boolean
  handoff_attempted: boolean
  handoff_expired: boolean
  released: boolean
}

/** O ManyChat recebe a mensagem e faz o External Request do fluxo, com o corpo do guia. */
async function manychatReceives (request: APIRequestContext, contact: WhatsappContact, message: string): Promise<AccessLinkCreated> {
  const response = await request.post(`${DJANGO}/api/auth/access/create/`, {
    data: {
      subscriber: {
        id: contact.subscriberId,
        whatsapp_id: `55${contact.phone}`,
        first_name: contact.name,
        last_name: ''
      },
      access_code: message,
      next: '/menu'
    }
  })
  expect(response.status(), await response.text()).toBe(200)
  const created = await response.json() as AccessLinkCreated
  // A mensagem trouxe a referência, e a sacola veio junto com ela.
  expect(created.handoff_attempted).toBe(true)
  expect(created.handoff_expired).toBe(false)
  expect(created.has_cart_context).toBe(true)
  return created
}

/** Chegou a finalizar, dentro: o contato já é ela, com o nome que o WhatsApp conhece, e o
 *  resumo do pedido traz o item da sacola. */
async function landsOnCheckoutWithBag (page: Page, testInfo: TestInfo, contact: WhatsappContact, name: string) {
  await expect(page).toHaveURL(/\/finalizar/, { timeout: 30_000 })
  await settled(page)
  await expect(page.getByRole('heading', { name: 'Finalize seu pedido', level: 1 })).toBeVisible()
  // O passo do contato já vem feito: nome e o número que mandou a mensagem.
  const local = contact.phone.slice(2)
  const phoneShown = `(${contact.phone.slice(0, 2)}) ${local.slice(0, 5)}-${local.slice(5)}`
  await expect(page.getByText(`${contact.name} ${phoneShown}`)).toBeVisible()
  await capture(page, testInfo, name)

  if (!isPhoneProject(testInfo)) {
    // No computador o resumo já está ao lado, sempre aberto.
    const summary = page.locator('aside').filter({ hasText: 'Seu pedido' })
    await expect(summary).toBeVisible()
    await expect(summary).toContainText(`1× ${PRODUCT}`)
    return
  }
  await page.getByRole('button', { name: 'Ver o resumo do pedido' }).click()
  const receipt = page.getByRole('dialog', { name: 'Seu pedido' })
  await expect(receipt).toBeVisible()
  await expect(receipt).toContainText(`1× ${PRODUCT}`)
  // A folha termina de subir antes da captura.
  await untilStill(page)
  await capture(page, testInfo, `${name}-resumo`)
  await page.keyboard.press('Escape')
  await expect(receipt).toBeHidden()
}

test.describe('no celular', () => {
  test.use({ userAgent: PHONE_USER_AGENT })

  test('J14: no celular, a cliente nova entra pelo WhatsApp e volta à loja com a sacola', async ({ page, request }, testInfo) => {
    test.skip(!isPhoneProject(testInfo), 'o caminho do celular roda na largura do celular')
    const contact = newContact()

    await test.step('a cliente põe um item na sacola', async () => {
      await addReadyProductFromMenu(page, testInfo, PRODUCT)
    })

    await test.step('vai finalizar, e a loja pede para entrar pelo WhatsApp', async () => {
      await goesToSignInFromBag(page, testInfo, /Voltar à loja/)
    })

    const message = await test.step('toca em "Abrir o WhatsApp" e a tela espera a mensagem', async () => {
      const sent = await opensWhatsapp(page, testInfo)
      await expect(page.locator('[data-login-whatsapp-waiting]')).toContainText('A loja abre com você dentro.')
      return sent
    })

    await test.step('confere antes de enviar, e a tela diz que a mensagem ainda não chegou', async () => {
      await checksBeforeTheMessageArrives(page, testInfo)
    })

    const created = await test.step('envia a mensagem, e o ManyChat a recebe', async () => {
      const link = await manychatReceives(request, contact, message)
      // No celular nada é liberado à distância: a entrada é pelo botão da resposta.
      expect(link.released).toBe(false)
      return link
    })

    await test.step('na resposta, toca em "Voltar à loja", e a loja abre com ela dentro', async () => {
      // O botão abre o navegador do celular numa aba nova, com o link da resposta.
      const store = await page.context().newPage()
      await store.goto(created.access_url)
      // Cliente nova, e o nome veio do WhatsApp: ela cai direto em finalizar, sem passo do nome.
      await landsOnCheckoutWithBag(store, testInfo, contact, 'voltou-a-loja-dentro')
      await store.close()
    })

    await test.step('a aba que esperava percebe sozinha e segue para finalizar', async () => {
      await page.bringToFront()
      await landsOnCheckoutWithBag(page, testInfo, contact, 'a-aba-que-esperava-entrou')
    })
  })
})

interface WhatsappButton { caption: string, url: string }

/** A resposta que a casa mandou pelo ManyChat, como chegou no WhatsApp da cliente: os
 *  botões da última mensagem de texto que o ManyChat falso da pilha guardou para ela
 *  (shopman/shop/tests/e2e/fake_manychat.py). */
async function replyButtons (request: APIRequestContext, contact: WhatsappContact): Promise<WhatsappButton[]> {
  let buttons: WhatsappButton[] = []
  await expect.poll(async () => {
    const response = await request.get(`${MANYCHAT}/__sent?subscriber=${contact.subscriberId}`)
    expect(response.status()).toBe(200)
    const { sent } = await response.json() as { sent: { endpoint: string, buttons?: WhatsappButton[] }[] }
    const replies = sent.filter(item => item.endpoint === '/fb/sending/sendContent')
    buttons = replies.at(-1)?.buttons ?? []
    return buttons.length
  }, { message: 'a resposta da casa chegou no WhatsApp da cliente' }).toBeGreaterThan(0)
  return buttons
}

function buttonNamed (buttons: WhatsappButton[], caption: RegExp): WhatsappButton {
  const button = buttons.find(b => caption.test(b.caption))
  expect(button, `botão ${caption} na resposta (${buttons.map(b => b.caption).join(', ')})`).toBeTruthy()
  return button!
}

/** Duas bolhas: a defesa ("Não reconhece este acesso?", com "Encerrar acesso") e, por
 *  último, a que libera. Os dois links são da loja, com a referência no fragmento. */
async function theReplyHasBothButtons (request: APIRequestContext, contact: WhatsappContact): Promise<WhatsappButton[]> {
  const buttons = await replyButtons(request, contact)
  expect(buttons.map(b => b.caption)).toEqual(['Encerrar acesso', expect.stringMatching(/^Liberar o Chrome/)])
  expect(buttonNamed(buttons, /^Liberar o Chrome/).url).toMatch(new RegExp(`^${escapeRegExp(STORE)}/liberar-acesso#.+`))
  expect(buttonNamed(buttons, /^Encerrar acesso$/).url).toMatch(new RegExp(`^${escapeRegExp(STORE)}/encerrar-acesso#.+`))
  return buttons
}

function escapeRegExp (text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** O celular da cliente: outro dispositivo, outro navegador, onde o WhatsApp abre os botões. */
async function phoneOf (browser: Browser): Promise<BrowserContext> {
  return await browser.newContext({ ...devices['Pixel 7'], locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' })
}

/** No celular, toca em "Liberar o Chrome": abrir a página É o toque, e ela confirma. */
async function releasesFromPhone (browser: Browser, testInfo: TestInfo, buttons: WhatsappButton[]) {
  const phone = await phoneOf(browser)
  try {
    const tap = await phone.newPage()
    await tap.goto(buttonNamed(buttons, /^Liberar o Chrome/).url)
    await settled(tap)
    await expect(tap.getByRole('heading', { name: 'Pronto, pode voltar ao computador', level: 1 })).toBeVisible()
    // A referência sai da barra de endereço assim que é lida.
    expect(new URL(tap.url()).hash).toBe('')
    await capture(tap, testInfo, 'no-celular-liberou-o-chrome')
  } finally {
    await phone.close()
  }
}

test('J14: no computador, a mensagem chega e a aba só entra com o toque em "Liberar"', async ({ page, request, browser }, testInfo) => {
  test.skip(isPhoneProject(testInfo), 'o caminho do computador roda na largura do computador')
  const contact = newContact()

  await test.step('a cliente põe um item na sacola', async () => {
    await addReadyProductFromMenu(page, testInfo, PRODUCT)
  })

  await test.step('vai finalizar, e a loja pede para entrar pelo WhatsApp', async () => {
    await goesToSignInFromBag(page, testInfo, /Liberar o Chrome/)
  })

  const message = await test.step('toca em "Abrir o WhatsApp" e a tela espera a mensagem', async () => {
    const sent = await opensWhatsapp(page, testInfo)
    await expect(page.locator('[data-login-whatsapp-waiting]')).toContainText('Esta tela entra logo depois.')
    return sent
  })

  await test.step('confere antes de enviar, e a tela diz que a mensagem ainda não chegou', async () => {
    await checksBeforeTheMessageArrives(page, testInfo)
  })

  await test.step('envia a mensagem, e o ManyChat a recebe', async () => {
    const link = await manychatReceives(request, contact, message)
    // A aba deste computador fica liberável, esperando o toque no celular.
    expect(link.released).toBe(true)
  })

  await test.step('sem o toque em "Liberar", a aba continua do lado de fora e diz que a mensagem chegou', async () => {
    // A conferência automática pode já ter visto a mensagem; o botão é o mesmo.
    const check = page.locator('[data-login-whatsapp-check]')
    await check.click()
    const waiting = page.locator('[data-login-whatsapp-waiting]')
    // #3271: a tela dizia "Conferimos agora e sua mensagem ainda não chegou".
    await expect(waiting.locator('[data-login-whatsapp-arrived]')).toContainText('Sua mensagem chegou')
    await expect(waiting.locator('[data-login-whatsapp-arrived]')).toContainText('toque em “Liberar o Chrome”')
    await expect(page.locator('[data-login-whatsapp-not-arrived]')).toHaveCount(0)
    await expect(waiting).not.toContainText('ainda não chegou')
    await expect(check).toHaveText('Já liberei. Conferir agora')
    await expect(check).toBeEnabled()
    // A ajuda abaixo não desmente o "Sua mensagem chegou": pergunta pela resposta.
    const support = page.locator('[data-login-support]')
    await expect(support).toContainText('Não recebeu a resposta no WhatsApp?')
    await expect(support).not.toContainText('Enviou e nada aconteceu?')
    await expect(support.getByRole('link', { name: 'Falar com a loja' })).toBeVisible()
    await expect(page).toHaveURL(/\/entrar/)
    await untilStill(page)
    await capture(page, testInfo, 'mensagem-chegou-sem-liberar')
  })

  const buttons = await test.step('a resposta chega no WhatsApp com "Liberar o Chrome" e "Encerrar acesso"', async () => {
    return await theReplyHasBothButtons(request, contact)
  })

  await test.step('no celular, toca em "Liberar o Chrome"', async () => {
    await releasesFromPhone(browser, testInfo, buttons)
  })

  await test.step('a aba que esperava entra sozinha e segue para finalizar com a sacola', async () => {
    await page.bringToFront()
    await landsOnCheckoutWithBag(page, testInfo, contact, 'o-chrome-entrou')
  })
})

test('J14: no computador, "Não foi você?" desfaz a entrada que o toque liberou', async ({ page, request, browser }, testInfo) => {
  test.skip(isPhoneProject(testInfo), 'o caminho do computador roda na largura do computador')
  const contact = newContact()

  await test.step('a cliente põe um item na sacola', async () => {
    await addReadyProductFromMenu(page, testInfo, PRODUCT)
  })

  await test.step('vai finalizar, e a loja pede para entrar pelo WhatsApp', async () => {
    await goesToSignInFromBag(page, testInfo, /Liberar o Chrome/)
  })

  const message = await test.step('toca em "Abrir o WhatsApp" e a tela espera a mensagem', async () => {
    return await opensWhatsapp(page, testInfo)
  })

  await test.step('envia a mensagem, e o ManyChat a recebe', async () => {
    const link = await manychatReceives(request, contact, message)
    expect(link.released).toBe(true)
  })

  const buttons = await test.step('a resposta chega no WhatsApp com "Liberar o Chrome" e "Encerrar acesso"', async () => {
    return await theReplyHasBothButtons(request, contact)
  })

  await test.step('o toque em "Liberar o Chrome" deixa a aba entrar', async () => {
    await releasesFromPhone(browser, testInfo, buttons)
    await page.bringToFront()
    await expect(page).toHaveURL(/\/finalizar/, { timeout: 30_000 })
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Finalize seu pedido', level: 1 })).toBeVisible()
  })

  await test.step('no celular, a dona do número toca em "Encerrar acesso" e confirma', async () => {
    const phone = await phoneOf(browser)
    try {
      const tap = await phone.newPage()
      await tap.goto(buttonNamed(buttons, /^Encerrar acesso$/).url)
      await settled(tap)
      // Abrir o link não derruba ninguém (a prévia do WhatsApp também o abre): é o toque.
      await expect(tap.getByRole('heading', { name: 'Não foi você que entrou?', level: 1 })).toBeVisible()
      await capture(tap, testInfo, 'no-celular-nao-foi-voce')
      await tap.getByRole('button', { name: 'Encerrar esse acesso' }).click()
      await expect(tap.getByRole('heading', { name: 'Acesso encerrado', level: 1 })).toBeVisible()
      await capture(tap, testInfo, 'no-celular-acesso-encerrado')
    } finally {
      await phone.close()
    }
  })

  await test.step('no computador, a aba que tinha entrado fica do lado de fora', async () => {
    await page.reload()
    await expect(page).toHaveURL(/\/entrar\?next=/)
    await settled(page)
    await expect(page.getByRole('heading', { name: 'Entre pelo WhatsApp', level: 1 })).toBeVisible()
    await capture(page, testInfo, 'a-aba-saiu')
  })
})
