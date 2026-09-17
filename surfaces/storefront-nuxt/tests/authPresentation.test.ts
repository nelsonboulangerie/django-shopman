import { describe, expect, it } from 'vitest'
import {
  LOGIN_ADULT_DECLARATION,
  LOGIN_ADULT_DECLARATION_LEAD,
  LOGIN_TERMS_LINK_LABEL,
  RESEND_COOLDOWN_MS,
  accessLinkLanding,
  authErrorView,
  authStep,
  codeSentPrefix,
  otpValidUntilDisplay,
  resendCooldown,
  welcomeCanContinue,
  welcomeNameValue,
  welcomeProfilePatch
} from '../app/presentation/auth'

describe('authStep', () => {
  it('starts on the phone step', () => {
    expect(authStep({ requestedPhone: '', verified: false, requiresWelcome: false })).toBe('phone')
  })

  it('moves to the code step once a code was requested', () => {
    expect(authStep({ requestedPhone: '+5543984049009', verified: false, requiresWelcome: false })).toBe('code')
  })

  it('opens the welcome gate only after a verified session asks for it', () => {
    expect(authStep({ requestedPhone: '+5543984049009', verified: true, requiresWelcome: true })).toBe('welcome')
    expect(authStep({ requestedPhone: '+5543984049009', verified: false, requiresWelcome: true })).toBe('code')
    expect(authStep({ requestedPhone: '+5543984049009', verified: true, requiresWelcome: false })).toBe('code')
  })
})

describe('authErrorView', () => {
  it('treats HTTP 429 as calm rate-limit recovery', () => {
    const view = authErrorView({ status: 429, detail: 'Muitas tentativas. Aguarde alguns minutos.' }, 'fallback')
    expect(view.kind).toBe('rate_limit')
    expect(view.title).toBe('Aguarde um instante')
    expect(view.message).toBe('Muitas tentativas. Aguarde alguns minutos.')
  })

  it('maps field hints from the API to specific kinds', () => {
    expect(authErrorView({ status: 400, field: 'phone', detail: 'Telefone inválido.' }, 'x').kind).toBe('invalid_phone')
    expect(authErrorView({ status: 400, field: 'code', detail: 'Informe os 6 números do código.' }, 'x').kind).toBe('invalid_code')
  })

  it('falls back to a generic view with the provided message', () => {
    const view = authErrorView({ status: 400, detail: '' }, 'Não foi possível enviar o código.')
    expect(view.kind).toBe('generic')
    expect(view.message).toBe('Não foi possível enviar o código.')
  })

  it('prefers the API detail over the fallback', () => {
    expect(authErrorView({ status: 400, detail: 'Código expirado.' }, 'x').message).toBe('Código expirado.')
  })
})

describe('resendCooldown', () => {
  it('is ready when nothing was sent yet', () => {
    expect(resendCooldown(null, 1000)).toEqual({ ready: true, remainingSeconds: 0 })
  })

  it('counts down whole seconds while the cooldown runs', () => {
    const sentAt = 10_000
    expect(resendCooldown(sentAt, sentAt + 1)).toEqual({ ready: false, remainingSeconds: 30 })
    expect(resendCooldown(sentAt, sentAt + 12_400)).toEqual({ ready: false, remainingSeconds: 18 })
  })

  it('releases exactly after the cooldown window', () => {
    const sentAt = 10_000
    expect(resendCooldown(sentAt, sentAt + RESEND_COOLDOWN_MS)).toEqual({ ready: true, remainingSeconds: 0 })
  })
})

describe('otpValidUntilDisplay', () => {
  it('formats the expiry as local HH:mm', () => {
    expect(otpValidUntilDisplay('2026-06-12T21:49:58.528337+00:00')).toMatch(/^\d{2}:\d{2}$/)
  })

  it('returns empty for blank or invalid input', () => {
    expect(otpValidUntilDisplay('')).toBe('')
    expect(otpValidUntilDisplay(null)).toBe('')
    expect(otpValidUntilDisplay('não-é-data')).toBe('')
  })
})

describe('welcomeNameValue', () => {
  it('trims and collapses internal whitespace', () => {
    expect(welcomeNameValue('  Maria   Clara ')).toBe('Maria Clara')
  })

  it('returns empty for blank input', () => {
    expect(welcomeNameValue('   ')).toBe('')
  })
})

describe('codeSentPrefix', () => {
  it('separa o canal do "para" com um espaço', () => {
    expect(codeSentPrefix('SMS')).toBe('Código enviado por SMS para')
    expect(codeSentPrefix('WhatsApp')).toBe('Código enviado por WhatsApp para')
  })

  it('omite o canal quando o servidor ainda não disse por onde mandou', () => {
    expect(codeSentPrefix('')).toBe('Código enviado para')
    expect(codeSentPrefix(null)).toBe('Código enviado para')
    expect(codeSentPrefix('   ')).toBe('Código enviado para')
  })
})

describe('accessLinkLanding', () => {
  it('keeps the backend destination when no welcome is pending', () => {
    expect(accessLinkLanding('/finalizar', false)).toBe('/finalizar')
  })

  it('falls back to home when the redirect is empty', () => {
    expect(accessLinkLanding('', false)).toBe('/')
  })

  it('routes through the welcome gate preserving the destination', () => {
    expect(accessLinkLanding('/pedido/NB-123', true)).toBe('/entrar?welcome=1&next=%2Fpedido%2FNB-123')
  })

  it('welcomes with home as destination when the redirect is empty', () => {
    expect(accessLinkLanding('', true)).toBe('/entrar?welcome=1&next=%2F')
  })

  it('does not re-wrap a destination that is already the login screen', () => {
    expect(accessLinkLanding('/entrar?welcome=1&next=%2Ffinalizar', true)).toBe('/entrar?welcome=1&next=%2Ffinalizar')
  })
})

// ── A declaração de maioridade, feita ao ENTRAR ────────────────────────────
//
// Decisão do dono (16/09): pedir data de nascimento para receber novidades é
// atrito demais. A prova de maioridade é a declaração feita ao entrar, e a
// frase é fixa — o servidor carimba a versão que a representa.

describe('LOGIN_ADULT_DECLARATION', () => {
  it('is exactly the sentence the server version stands for', () => {
    expect(LOGIN_ADULT_DECLARATION).toBe('Ao continuar, você confirma que é maior de idade e aceita os Termos de uso.')
    expect(`${LOGIN_ADULT_DECLARATION_LEAD} ${LOGIN_TERMS_LINK_LABEL}.`).toBe(LOGIN_ADULT_DECLARATION)
  })

  it('never says "18", "anos" or "adulto" to the customer', () => {
    expect(LOGIN_ADULT_DECLARATION).not.toMatch(/18|anos|adult/i)
  })
})

// ── A pergunta de novidades no gate ────────────────────────────────────────
//
// Medido no alpha em 16/09: 58 clientes ativos, 1 aniversário, 5 consentimentos
// de WhatsApp. O gate passa a perguntar UMA vez; a caixa nasce desligada e é SÓ
// consentimento — sem data de nascimento (a maioridade foi declarada ao entrar).

describe('welcomeCanContinue', () => {
  const base = { asksName: false, asksMarketing: true, name: '', marketingOptIn: false }

  it('lets the marketing-only gate continue with the box off', () => {
    expect(welcomeCanContinue(base)).toBe(true)
  })

  it('lets it continue with the box on too — nothing else is asked', () => {
    expect(welcomeCanContinue({ ...base, marketingOptIn: true })).toBe(true)
  })

  it('still requires the name when the name was asked', () => {
    expect(welcomeCanContinue({ ...base, asksName: true })).toBe(false)
    expect(welcomeCanContinue({ ...base, asksName: true, name: '  Ana ' })).toBe(true)
  })
})

describe('welcomeProfilePatch', () => {
  it('sends nothing to the profile when only the question was answered', () => {
    expect(welcomeProfilePatch({ asksName: false, asksMarketing: true, name: '', marketingOptIn: true })).toBeNull()
  })

  it('sends the cleaned name when it was asked', () => {
    expect(welcomeProfilePatch({ asksName: true, asksMarketing: true, name: ' Ana  Silva ', marketingOptIn: true })).toEqual({ first_name: 'Ana Silva' })
  })

  it('sends nothing when the name was asked but left empty', () => {
    expect(welcomeProfilePatch({ asksName: true, asksMarketing: false, name: '   ', marketingOptIn: false })).toBeNull()
  })
})
