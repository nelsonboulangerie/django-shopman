// Máquina de estado da sessão do cliente (WP-S1): hidratação por home/auth,
// higienização de texto opcional ("null"/vazio → null) e reset. Sem rede.
import { describe, it, expect, beforeEach } from 'vitest'

async function loadSession () {
  const { useShopSession } = await import('~/composables/useShopSession')
  const s = useShopSession()
  s.reset()
  return s
}

function home (authenticated: boolean, marketingPromptPending = false) {
  return {
    omotenashi: {
      audience: authenticated ? 'known' : 'anon',
      customer_name: authenticated ? 'Ana' : null,
      marketing_prompt_pending: marketingPromptPending
    },
    shop: { name: 'Nelson' },
    shop_status: { is_open: true },
    notices: [{ id: 1 }],
    opening_hours: [{ label: 'seg', hours: '8-18' }],
    last_order_ref: authenticated ? 'ORD-1' : null,
    public_config: { whatsapp_url: 'https://wa.me/1' }
  } as never
}

describe('useShopSession', () => {
  beforeEach(async () => { await loadSession() })

  it('starts with the Nelson brand fallback before the API responds', async () => {
    const s = await loadSession()
    expect(s.shop.value?.brand_name).toBe('Nelson Boulangerie')
    expect(s.shop.value?.design_tokens?.cta).toBe('139 107 46')
  })

  it('hydrates an authenticated customer from home', async () => {
    const s = await loadSession()
    s.setFromHome(home(true))
    expect(s.isAuthenticated.value).toBe(true)
    expect(s.customerName.value).toBe('Ana')
    expect(s.lastOrderRef.value).toBe('ORD-1')
    expect(s.homeNotices.value).toHaveLength(1)
    expect(s.publicConfig.value?.whatsapp_url).toBe('https://wa.me/1')
  })

  it('anon home clears identity but keeps shop metadata', async () => {
    const s = await loadSession()
    s.setFromHome(home(false))
    expect(s.isAuthenticated.value).toBe(false)
    expect(s.customerName.value).toBeNull()
    expect(s.lastOrderRef.value).toBeNull()
    expect(s.shop.value?.name).toBe('Nelson')
  })

  it('can preserve an auth session when a late anon home response only hydrates shop metadata', async () => {
    const s = await loadSession()
    s.setFromAuthSession({ is_authenticated: true, customer_name: 'Bruno', customer_phone: '43999' })
    s.setFromHome(home(false), { preserveAuthenticated: true })
    expect(s.isAuthenticated.value).toBe(true)
    expect(s.customerName.value).toBe('Bruno')
    expect(s.customerPhone.value).toBe('43999')
    expect(s.shop.value?.name).toBe('Nelson')
  })

  it('sanitizes the literal string "null" to a real null name', async () => {
    const s = await loadSession()
    s.setFromAuthSession({ is_authenticated: true, customer_name: 'null', customer_phone: '  ' })
    expect(s.customerName.value).toBeNull()
    expect(s.customerPhone.value).toBeNull()
  })

  it('setFromAuthSession with is_authenticated=false wipes the session', async () => {
    const s = await loadSession()
    s.setFromAuthSession({ is_authenticated: true, customer_name: 'Bruno', customer_phone: '43999' })
    expect(s.isAuthenticated.value).toBe(true)
    s.setFromAuthSession({ is_authenticated: false })
    expect(s.isAuthenticated.value).toBe(false)
    expect(s.customerName.value).toBeNull()
    expect(s.customerPhone.value).toBeNull()
  })

  it('setIdentity patches only provided fields', async () => {
    const s = await loadSession()
    s.setFromAuthSession({ is_authenticated: true, customer_name: 'Bruno', customer_phone: '43999' })
    s.setIdentity({ name: 'Bruna' })
    expect(s.customerName.value).toBe('Bruna')
    expect(s.customerPhone.value).toBe('43999') // preservado
  })

  it('requires_welcome flows through and reset clears everything', async () => {
    const s = await loadSession()
    s.setFromAuthSession({ is_authenticated: true, requires_welcome: true, welcome_suggested_name: 'Ana' })
    expect(s.requiresWelcome.value).toBe(true)
    expect(s.welcomeSuggestedName.value).toBe('Ana')
    s.reset()
    expect(s.requiresWelcome.value).toBe(false)
    expect(s.isAuthenticated.value).toBe(false)
  })

  it('the marketing question rides along but never opens the welcome gate', async () => {
    const s = await loadSession()
    s.setFromAuthSession({ is_authenticated: true, customer_name: 'Ana', requires_welcome: false, welcome_asks_name: false, welcome_asks_marketing: true })
    // O gate do login é só o nome; a pergunta de novidades é do sheet.
    expect(s.requiresWelcome.value).toBe(false)
    expect(s.welcomeAsksName.value).toBe(false)
    expect(s.welcomeAsksMarketing.value).toBe(true)
    // Responder o gate do nome não mexe na pergunta de novidades…
    s.setIdentity({ requiresWelcome: false })
    expect(s.welcomeAsksMarketing.value).toBe(true)
    // …e responder (ou fechar) o sheet apaga só ela.
    s.markMarketingPromptAnswered()
    expect(s.welcomeAsksMarketing.value).toBe(false)
    expect(s.isAuthenticated.value).toBe(true)
  })

  // Carga fria: quem volta com aparelho reconhecido não passa pelo login. A
  // pergunta de novidades tem de chegar pela home, que vem em toda visita.
  it('the home alone brings the marketing question on a cold load', async () => {
    const s = await loadSession()
    s.setFromHome(home(true, true))
    expect(s.isAuthenticated.value).toBe(true)
    expect(s.welcomeAsksMarketing.value).toBe(true)
    // Nada disso abre o gate do login.
    expect(s.requiresWelcome.value).toBe(false)

    s.setFromHome(home(true, false))
    expect(s.welcomeAsksMarketing.value).toBe(false)
  })

  it('a late home (or session) never brings back a question answered in this browser session', async () => {
    const s = await loadSession()
    s.setFromHome(home(true, true))
    s.markMarketingPromptAnswered()
    expect(s.welcomeAsksMarketing.value).toBe(false)

    // Resposta lida antes do carimbo chegando depois: não reabre.
    s.setFromHome(home(true, true))
    expect(s.welcomeAsksMarketing.value).toBe(false)
    s.setFromAuthSession({ is_authenticated: true, customer_name: 'Ana', welcome_asks_name: false, welcome_asks_marketing: true })
    expect(s.welcomeAsksMarketing.value).toBe(false)
  })

  it('an anonymous home never asks, and a preserved auth route keeps what it knew', async () => {
    const s = await loadSession()
    s.setFromHome(home(false, true))
    expect(s.welcomeAsksMarketing.value).toBe(false)

    s.setFromAuthSession({ is_authenticated: true, customer_name: 'Ana', welcome_asks_name: false, welcome_asks_marketing: true })
    s.setFromHome(home(false), { preserveAuthenticated: true })
    expect(s.welcomeAsksMarketing.value).toBe(true)
  })

  it('answering the name gate clears the name question only', async () => {
    const s = await loadSession()
    s.setFromAuthSession({ is_authenticated: true, customer_name: '', requires_welcome: true, welcome_asks_name: true, welcome_asks_marketing: true })
    expect(s.requiresWelcome.value).toBe(true)
    s.setIdentity({ name: 'Ana', requiresWelcome: false })
    expect(s.requiresWelcome.value).toBe(false)
    expect(s.welcomeAsksName.value).toBe(false)
    expect(s.welcomeAsksMarketing.value).toBe(true)
  })

  it('reads a payload without the asks_* flags as the old name-only gate', async () => {
    const s = await loadSession()
    s.setFromAuthSession({ is_authenticated: true, requires_welcome: true, welcome_suggested_name: '' })
    expect(s.welcomeAsksName.value).toBe(true)
    expect(s.welcomeAsksMarketing.value).toBe(false)
  })
})
