// `conta/seguranca` é a tela mais sensível da loja para o cliente, e até aqui não
// tinha NENHUM teste de componente. As duas regressões que ela pode ter são também
// as duas piores da loja inteira:
//
//   1. a pessoa pensa que apagou a conta e não apagou — a tela diz "pronto" sobre
//      uma exclusão que o servidor recusou;
//   2. a pessoa não reconhece um acesso legítimo e se assusta — a linha do aparelho
//      inventa um lugar, ou some com a data que responde "fui eu que entrei?".
//
// Por isso o que se trava aqui não é linha de código coberta: é cada AFIRMAÇÃO que
// a tela faz ao titular. Os estados vêm do servidor de verdade — `storefront/api/
// account.py` e `storefront/services/account_privacy.py` — e não de invenção: 503
// `account_deletion_incomplete`, 409 `account_deletion_blocked`,
// `privacy_requests_available: false`.
//
// ⚠️ A loja diz "aparelho" ao cliente (decisão do dono, exenção declarada da trava de
// vocabulário do operator-kit, que cita esta página pelo nome). Nada aqui nega essa
// palavra — negá-la derruba a trava do kit.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'
import { setResponseStatus } from 'h3'

import SecurityPage from '~/pages/conta/seguranca.vue'
import type { AccountDeviceProjection } from '~/types/shopman'

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn() }))
mockNuxtImport('navigateTo', () => navigateToMock)

// A copy da tela vem do registro omotenashi (configurável no Admin), e a tela só cai
// no fallback dela enquanto carrega. Servir aqui os MESMOS padrões de `_devices_copy()`
// mantém o teste falando do contrato, e não de um texto inventado para o teste.
const COPY = {
  page_message: 'Verifique os aparelhos confiáveis e controle seus dados pessoais.',
  empty_title: 'Nenhum aparelho confiável',
  empty_message: 'Quando você optar por confiar neste aparelho no login, ele aparecerá aqui.',
  current_badge: 'Este aparelho',
  last_used_prefix: 'Último uso em',
  near_prefix: 'Próximo a',
  registered_prefix: 'Registrado em',
  revoke_cta: 'Remover',
  revoke_all_cta: 'Remover todos os aparelhos',
  revoke_confirm: 'Remover este aparelho?',
  revoke_all_confirm: 'Remover todos os aparelhos?',
  unknown_label: 'Aparelho desconhecido',
  delete_warning: 'Apagamos seu nome, telefone, e-mail e endereços, inclusive dos pedidos antigos, e você sai da loja neste aparelho.'
}

function device (overrides: Partial<AccountDeviceProjection> = {}): AccountDeviceProjection {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    label: 'Chrome no Android',
    created_at: '2026-09-20T09:00:00-03:00',
    created_at_display: '20/09/2026 às 09:00',
    last_used_at: '2026-09-22T14:30:00-03:00',
    last_used_at_display: '22/09/2026 às 14:30',
    approximate_city: '',
    is_current: false,
    ...overrides
  }
}

type Reply = { status?: number, body: Record<string, unknown> }

let servedDevices: AccountDeviceProjection[] = []
let privacyAvailable: boolean | undefined
let deleteReply: Reply
let stepUpReply: Reply
let deleteCalls = 0
let requestCodeCalls = 0
let assignedUrl = ''

function reply (event: unknown, r: Reply) {
  if (r.status && r.status !== 200) setResponseStatus(event as never, r.status)
  return r.body
}

registerEndpoint('/api/v1/account/devices/', () => ({
  devices: servedDevices,
  copy: COPY,
  privacy_requests_available: privacyAvailable
}))
registerEndpoint('/api/v1/account/passkeys/', () => ({ passkeys: [] }))
registerEndpoint('/api/auth/request-code/', {
  method: 'POST',
  handler: () => { requestCodeCalls += 1; return { ok: true } }
})
registerEndpoint('/api/v1/account/step-up/', {
  method: 'POST',
  handler: event => reply(event, stepUpReply)
})
registerEndpoint('/api/v1/account/delete/', {
  method: 'POST',
  handler: (event) => { deleteCalls += 1; return reply(event, deleteReply) }
})

const mounted: Array<{ unmount: () => void }> = []

/** O diálogo da reka-ui é teleportado para o `body`: o wrapper da página não o vê. */
function body () {
  return new DOMWrapper(document.body)
}

async function openSecurity (devices: AccountDeviceProjection[] = []) {
  servedDevices = devices
  clearNuxtData()
  const page = await mountSuspended(SecurityPage)
  mounted.push(page)
  await flushPromises()
  return page
}

type Clickable = {
  text: () => string
  trigger: (e: string) => Promise<void>
  attributes: (a: string) => string | undefined
}

function buttonBy (scope: { findAll: (s: string) => unknown[] }, label: string) {
  const all = scope.findAll('button') as Clickable[]
  return all.find(b => b.text().trim() === label) || all.find(b => b.text().trim().includes(label))
}

// Confirmar o step-up encadeia vários `await` antes do efeito visível: o header de
// CSRF, o POST do código, a AÇÃO pendente e o fetch dela. Um `flushPromises` só
// drena o primeiro salto, e a tela ainda parece parada no diálogo — foi assim que
// este teste "reprovou" a página inteira antes de o gesto sequer ter terminado.
async function settle (times = 6) {
  for (let i = 0; i < times; i += 1) await flushPromises()
}

async function fillCode () {
  const casas = body().findAll('input[data-slot="pin-input-input"]')
  expect(casas).toHaveLength(6)
  for (const [i, casa] of casas.entries()) await casa.setValue(String(i + 1))
  await flushPromises()
}

/** Do gesto "Excluir minha conta" até o POST: ack → step-up → código → Confirmar. */
async function runDeletion (page: Awaited<ReturnType<typeof openSecurity>>) {
  await buttonBy(page, 'Excluir minha conta')!.trigger('click')
  await flushPromises()

  await body().find('#delete-account-ack').trigger('click')
  await flushPromises()

  await buttonBy(body(), 'Continuar')!.trigger('click')
  await settle()

  await fillCode()

  await buttonBy(body(), 'Confirmar')!.trigger('click')
  await settle()
}

beforeEach(async () => {
  document.cookie = 'csrftoken=testtoken'
  navigateToMock.mockReset()
  deleteCalls = 0
  requestCodeCalls = 0
  assignedUrl = ''
  privacyAvailable = true
  deleteReply = { body: { ok: true, receipt_ref: 'rcpt-1', replayed: false } }
  stepUpReply = { body: { ok: true } }
  // A exportação é uma NAVEGAÇÃO do navegador (download), não um fetch: o que prova
  // que ela partiu é o endereço que a tela mandou o navegador abrir.
  Object.defineProperty(window, 'location', {
    configurable: true,
    writable: true,
    value: { href: 'http://localhost/conta/seguranca', assign: (url: string) => { assignedUrl = String(url) } }
  })
  const { useShopSession } = await import('~/composables/useShopSession')
  const session = useShopSession()
  session.reset()
  session.setFromAuthSession({ is_authenticated: true, customer_name: 'Ana', customer_phone: '+5543984049009' })
})

afterEach(() => {
  for (const page of mounted.splice(0)) page.unmount()
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('conta/seguranca — o aparelho confiável', () => {
  it('diz o navegador e as duas datas, cada uma dizendo de que é', async () => {
    const page = await openSecurity([device()])

    expect(page.text()).toContain('Chrome no Android')
    // Sem os prefixos a linha vira "22/09/2026 às 14:30 · 20/09/2026 às 09:00": duas
    // datas, e a primeira sem dizer do que é — justamente a que responde "fui eu?".
    expect(page.text()).toContain('Último uso em 22/09/2026 às 14:30')
    expect(page.text()).toContain('Registrado em 20/09/2026 às 09:00')
  })

  it('diz a cidade aproximada quando a projeção traz a leitura confiável', async () => {
    const page = await openSecurity([device({ approximate_city: 'Londrina, PR · Brasil' })])

    expect(page.text()).toContain('Próximo a Londrina, PR · Brasil')
  })

  it('não diz NADA de lugar quando a cidade vem vazia', async () => {
    // Vazio é o caso comum e legítimo: a leitura de IP só vira rótulo quando o raio de
    // precisão é pequeno o bastante, e em celular normalmente não é. A ausência é
    // deliberada — "Local desconhecido" assustaria quem não fez nada errado.
    const page = await openSecurity([device({ approximate_city: '' })])

    expect(page.text()).not.toContain('Próximo a')
    expect(page.text()).not.toContain('desconhecido')
    // Controle positivo: a linha renderizou mesmo (o teste acima não passa por vazio).
    expect(page.text()).toContain('Último uso em 22/09/2026 às 14:30')
  })

  it('põe o selo "Este aparelho" só no que a pessoa está usando', async () => {
    const page = await openSecurity([
      device({ id: 'atual', label: 'Safari no iPhone', is_current: true }),
      device({ id: 'outro', label: 'Chrome no Windows', is_current: false })
    ])

    const comSelo = page.findAll('[data-slot="item"]').filter(i => i.text().includes('Este aparelho'))
    expect(comSelo).toHaveLength(1)
    expect(comSelo[0]!.text()).toContain('Safari no iPhone')
    expect(comSelo[0]!.text()).not.toContain('Chrome no Windows')
  })
})

describe('conta/seguranca — excluir a conta', () => {
  it('conclui, encerra a sessão e leva para a loja', async () => {
    const page = await openSecurity([device()])
    const { useShopSession } = await import('~/composables/useShopSession')

    await runDeletion(page)

    expect(deleteCalls).toBe(1)
    expect(navigateToMock).toHaveBeenCalledWith('/')
    expect(useShopSession().isAuthenticated.value).toBe(false)
  })

  it('falha parcial NÃO diz "pronto": avisa, mantém a sessão e não sai da tela', async () => {
    // 503 `account_deletion_incomplete` — o provedor não confirmou o apagamento. É a
    // regressão que mais assusta: cliente que pensa que apagou e não apagou.
    const recusa = (
      'Não conseguimos concluir a exclusão agora. Nenhuma exclusão parcial foi '
      + 'confirmada, e nossa equipe já foi avisada. Tente novamente em alguns minutos.'
    )
    deleteReply = { status: 503, body: { detail: recusa, error: { code: 'account_deletion_incomplete' } } }
    const page = await openSecurity([device()])
    const { useShopSession } = await import('~/composables/useShopSession')

    await runDeletion(page)

    expect(deleteCalls).toBe(1)
    expect(body().text()).toContain(recusa)
    expect(navigateToMock).not.toHaveBeenCalled()
    expect(useShopSession().isAuthenticated.value).toBe(true)
  })

  it('bloqueio por pedido em andamento diz o que fazer, e não conclui', async () => {
    // 409 `account_deletion_blocked`/`active_order` — pré-condição que o cliente
    // resolve sozinho, então a frase traz o gesto, e não um "tente de novo" cego.
    const bloqueio = (
      'Ainda existe um pedido em andamento. Conclua ou cancele esse pedido antes '
      + 'de excluir a conta.'
    )
    deleteReply = {
      status: 409,
      body: { detail: bloqueio, error: { code: 'account_deletion_blocked', reason: 'active_order' } }
    }
    const page = await openSecurity([device()])

    await runDeletion(page)

    expect(body().text()).toContain(bloqueio)
    expect(navigateToMock).not.toHaveBeenCalled()
  })
})

describe('conta/seguranca — dados e privacidade', () => {
  it('exportar pede confirmação de identidade ANTES de baixar', async () => {
    const page = await openSecurity([device()])

    await buttonBy(page, 'Exportar meus dados')!.trigger('click')
    await flushPromises()

    // O código sai na hora em que o diálogo abre; o download ainda não partiu.
    expect(requestCodeCalls).toBe(1)
    expect(body().text()).toContain('Confirme sua identidade')
    expect(assignedUrl).toBe('')

    await fillCode()
    await buttonBy(body(), 'Confirmar')!.trigger('click')
    await settle()

    expect(assignedUrl).toContain('/api/v1/account/export/')
  })

  it('sem recibo assinável, nenhuma das duas ações é oferecida', async () => {
    // `privacy_requests_available: false` = a chave do recibo está ausente/inválida.
    // O recibo é parte do contrato do art. 18, não telemetria: sem ele a casa não
    // oferece a ação, em vez de prometer e falhar no meio.
    privacyAvailable = false
    const page = await openSecurity([device()])

    expect(page.text()).toContain('Solicitações temporariamente indisponíveis')
    expect(buttonBy(page, 'Exportar meus dados')!.attributes('disabled')).toBeDefined()
    expect(buttonBy(page, 'Excluir minha conta')!.attributes('disabled')).toBeDefined()
  })
})
