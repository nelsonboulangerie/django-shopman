import { devices, expect, test, type APIRequestContext, type Page, type TestInfo } from '@playwright/test'
import { addReadyProductFromMenu } from './support/customer'
import { capture, newCustomerPhone, settled } from './support/stack'

// J16 · Quem toca em Finalizar e entra pelo WhatsApp cai em Finalizar (DEV-2026-092).
//
// A fala do dono: a cliente montou o pedido, tocou em Finalizar, a loja pediu para entrar
// pelo WhatsApp, ela entrou, e em vez de cair no checkout precisou tocar em Finalizar de
// novo. O destino tem de sobreviver à ida e volta do WhatsApp, onde quer que a entrada
// termine.
//
// A J14 já prova o caminho em que tudo dá certo: a mensagem pronta chega ao ManyChat com a
// referência NB-…, o link da resposta carrega o destino, e a loja abre em /finalizar. Esta
// jornada cobre o que a J14 não cobre:
//
// 1. o link da resposta NÃO carrega o destino. A referência NB-… é de uso único: a mesma
//    mensagem processada duas vezes (a cliente enviou de novo, o External Request do
//    ManyChat repetiu) deixa a segunda resposta sem o contexto do site, e o ManyChat manda
//    o destino genérico dele (`next: "/menu"`, docs/guides/whatsapp-access-link.md). O
//    mesmo acontece quando o texto da mensagem não chega ao External Request. A cliente
//    toca no botão da última resposta, e o celular abre a loja numa aba nova do MESMO
//    navegador (o Safari do iPhone faz assim). A sacola está lá, porque o cookie é o mesmo;
//    o destino também tem de estar;
// 2. o botão abre OUTRO navegador (o embutido do WhatsApp, pote de cookie próprio), com a
//    aba original esperando: a loja abre ali em /finalizar, com a sacola.
//
// O papel do ManyChat é o mesmo da J14: o POST que o External Request do fluxo faz ao Django.
const PRODUCT = 'Croissant' // pronto agora no seed `--profile qa`
const PHONE = devices['Pixel 7']
const DJANGO = (process.env.JOURNEY_DJANGO_URL || `http://127.0.0.1:${process.env.JOURNEYS_DJANGO_PORT || '8090'}`).replace(/\/$/, '')
const CART_LEFT_BEHIND = 'Sua sacola não veio desta vez'

interface WhatsappContact { phone: string, name: string, subscriberId: string }

function newContact (): WhatsappContact {
  const phone = newCustomerPhone()
  return { phone, name: 'Iolanda', subscriberId: `8${phone}` }
}

function isPhoneProject (testInfo: TestInfo): boolean {
  return (testInfo.project.use.viewport?.width ?? 0) < 768
}

/** Da sacola, toca em Finalizar: a loja pede para entrar, com o WhatsApp na frente. */
async function finalizeAsksToSignIn (page: Page, testInfo: TestInfo) {
  await page.getByRole('link', { name: 'Finalizar pedido' }).last().click()
  await expect(page).toHaveURL(/\/entrar\?next=(%2F|\/)finalizar/)
  await settled(page)
  await expect(page.getByRole('heading', { name: 'Entre pelo WhatsApp', level: 1 })).toBeVisible()
  await capture(page, testInfo, 'entrar-pelo-whatsapp')
}

/** Toca em "Abrir o WhatsApp"; o WhatsApp não abre de verdade, a mensagem pronta é lida do
 *  link. A aba passa a esperar a mensagem. */
async function sendsTheReadyMessage (page: Page): Promise<string> {
  const opened: string[] = []
  await page.context().route(/^https:\/\/(wa\.me|api\.whatsapp\.com)\//, async (route) => {
    opened.push(route.request().url())
    await route.abort()
  })
  const panel = page.locator('[data-login-whatsapp-open]')
  const popup = page.waitForEvent('popup')
  await panel.getByRole('link', { name: 'Abrir o WhatsApp' }).click()
  await (await popup).close()
  await page.bringToFront()
  await expect.poll(() => opened.length).toBeGreaterThan(0)
  await expect(page.locator('[data-login-whatsapp-waiting]')).toBeVisible()
  return new URL(opened[0]!).searchParams.get('text') ?? ''
}

interface AccessLinkCreated { access_url: string, handoff_expired: boolean, has_cart_context: boolean }

/** O External Request do fluxo do ManyChat, com o corpo do guia. */
async function manychatReceives (request: APIRequestContext, contact: WhatsappContact, message: string): Promise<AccessLinkCreated> {
  const response = await request.post(`${DJANGO}/api/auth/access/create/`, {
    data: {
      subscriber: { id: contact.subscriberId, whatsapp_id: `55${contact.phone}`, first_name: contact.name, last_name: '' },
      access_code: message,
      next: '/menu'
    }
  })
  expect(response.status(), await response.text()).toBe(200)
  return await response.json() as AccessLinkCreated
}

/** Em /finalizar, já dentro, com o item da sacola. */
async function landsOnCheckout (page: Page, testInfo: TestInfo, name: string) {
  await expect(page).toHaveURL(/\/finalizar/, { timeout: 30_000 })
  await settled(page)
  await expect(page.getByRole('heading', { name: 'Finalize seu pedido', level: 1 })).toBeVisible()
  await capture(page, testInfo, name)
  await page.getByRole('button', { name: 'Ver o resumo do pedido' }).click()
  const receipt = page.getByRole('dialog', { name: 'Seu pedido' })
  await expect(receipt).toContainText(`1× ${PRODUCT}`)
  await page.keyboard.press('Escape')
  await expect(receipt).toBeHidden()
}

test.describe('no celular', () => {
  test.use({ userAgent: PHONE.userAgent })

  test('J16: a resposta sem o contexto do site ainda abre em Finalizar, na aba nova do mesmo navegador', async ({ page, request }, testInfo) => {
    test.skip(!isPhoneProject(testInfo), 'o caminho do celular roda na largura do celular')
    const contact = newContact()

    await test.step('a cliente põe um item na sacola e toca em Finalizar', async () => {
      await addReadyProductFromMenu(page, testInfo, PRODUCT)
      await finalizeAsksToSignIn(page, testInfo)
    })

    const message = await test.step('abre o WhatsApp com a mensagem pronta', async () => {
      return await sendsTheReadyMessage(page)
    })

    const last = await test.step('a mesma mensagem chega duas vezes ao ManyChat', async () => {
      const first = await manychatReceives(request, contact, message)
      expect(first.has_cart_context).toBe(true)
      // A referência NB-… já foi usada: a segunda resposta vai sem o contexto do site.
      const second = await manychatReceives(request, contact, message)
      expect(second.handoff_expired).toBe(true)
      return second
    })

    await test.step('toca em "Voltar à loja" na última resposta, e a loja abre em Finalizar', async () => {
      // O WhatsApp abre o link numa aba nova do navegador do celular: o mesmo pote de cookie.
      const store = await page.context().newPage()
      await store.goto(last.access_url)
      await landsOnCheckout(store, testInfo, 'aba-nova-em-finalizar')
      // A sacola veio junto: a loja não diz que ela ficou para trás.
      await expect(store.getByText(CART_LEFT_BEHIND)).toHaveCount(0)
      await store.close()
    })

    await test.step('a aba que esperava percebe sozinha e segue para Finalizar', async () => {
      await page.bringToFront()
      await landsOnCheckout(page, testInfo, 'aba-que-esperava-em-finalizar')
    })
  })

  test('J16: o botão abre outro navegador, e a loja abre ali em Finalizar com a sacola', async ({ page, request, browser }, testInfo) => {
    test.skip(!isPhoneProject(testInfo), 'o caminho do celular roda na largura do celular')
    const contact = newContact()

    await test.step('a cliente põe um item na sacola e toca em Finalizar', async () => {
      await addReadyProductFromMenu(page, testInfo, PRODUCT)
      await finalizeAsksToSignIn(page, testInfo)
    })

    const created = await test.step('envia a mensagem pronta, e o ManyChat a recebe', async () => {
      const message = await sendsTheReadyMessage(page)
      return await manychatReceives(request, contact, message)
    })

    await test.step('o botão da resposta abre outro navegador, e a loja abre ali em Finalizar', async () => {
      // Outro pote de cookie: o navegador embutido do WhatsApp, ou outro app de navegador.
      const other = await browser.newContext({ ...PHONE, locale: 'pt-BR', timezoneId: 'America/Sao_Paulo' })
      try {
        const store = await other.newPage()
        await store.goto(created.access_url)
        await landsOnCheckout(store, testInfo, 'outro-navegador-em-finalizar')
      } finally {
        await other.close()
      }
    })
  })
})
