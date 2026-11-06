import { describe, expect, it } from 'vitest'
import {
  LOGIN_ADULT_DECLARATION,
  LOGIN_ADULT_DECLARATION_LEAD,
  LOGIN_TERMS_LINK_LABEL,
  RESEND_COOLDOWN_MS,
  accessLinkLanding,
  authErrorBelongsToPhoneField,
  authErrorKillsCode,
  authErrorOffersSupport,
  authErrorView,
  authStep,
  codeSentPrefix,
  otpValidUntilDisplay,
  isMarketingPromptRouteExcluded,
  pendingCodeFromCooldown,
  resendCooldown,
  restorePendingCode,
  resendWindowMs,
  welcomeNameFields,
  welcomeNameValue
} from '../app/presentation/auth'

describe('authStep', () => {
  it('starts on the phone step', () => {
    expect(authStep({ requestedPhone: '', verified: false, requiresWelcome: false })).toBe('phone')
  })

  it('moves to the code step once a code was requested', () => {
    expect(authStep({ requestedPhone: '+5543981234567', verified: false, requiresWelcome: false })).toBe('code')
  })

  it('opens the welcome gate only after a verified session asks for it', () => {
    expect(authStep({ requestedPhone: '+5543981234567', verified: true, requiresWelcome: true })).toBe('welcome')
    expect(authStep({ requestedPhone: '+5543981234567', verified: false, requiresWelcome: true })).toBe('code')
    expect(authStep({ requestedPhone: '+5543981234567', verified: true, requiresWelcome: false })).toBe('code')
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
    expect(resendCooldown(sentAt, sentAt + 1)).toEqual({ ready: false, remainingSeconds: 60 })
    expect(resendCooldown(sentAt, sentAt + 12_400)).toEqual({ ready: false, remainingSeconds: 48 })
  })

  it('releases exactly after the cooldown window', () => {
    const sentAt = 10_000
    expect(resendCooldown(sentAt, sentAt + RESEND_COOLDOWN_MS)).toEqual({ ready: true, remainingSeconds: 0 })
  })

  // O botão não pode liberar antes de o servidor aceitar: eram 30 s aqui contra
  // 60 s do gate G11, e o "Reenviar" dos 30-59 s voltava "Aguarde".
  it('follows the window the server declares', () => {
    const sentAt = 10_000
    const window = resendWindowMs(90)
    expect(window).toBe(90_000)
    expect(resendCooldown(sentAt, sentAt + 60_000, window)).toEqual({ ready: false, remainingSeconds: 30 })
    expect(resendCooldown(sentAt, sentAt + 90_000, window)).toEqual({ ready: true, remainingSeconds: 0 })
  })

  it('falls back to the doorman default when the server omits the window', () => {
    expect(resendWindowMs(undefined)).toBe(RESEND_COOLDOWN_MS)
    expect(resendWindowMs(null)).toBe(RESEND_COOLDOWN_MS)
    expect(resendWindowMs(Number.NaN)).toBe(RESEND_COOLDOWN_MS)
    expect(RESEND_COOLDOWN_MS).toBe(60_000)
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

describe('welcomeNameFields', () => {
  it('divide o nome inteiro pela regra da casa: primeiro token é o nome', () => {
    expect(welcomeNameFields('  Pablo   Valentini ')).toEqual({ first_name: 'Pablo', last_name: 'Valentini' })
  })

  it('erra do lado do sobrenome, como a regra do servidor', () => {
    expect(welcomeNameFields('Ana Maria Silva')).toEqual({ first_name: 'Ana', last_name: 'Maria Silva' })
  })

  it('um nome só não manda sobrenome (não apaga o que está no cadastro)', () => {
    expect(welcomeNameFields('Talita')).toEqual({ first_name: 'Talita' })
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

// ── O convite de novidades não é passo do login ────────────────────────────
//
// Ele sobe como sheet na página de destino e nunca interrompe o que a pessoa
// veio fazer: fora das portas de entrada, do checkout e do pedido.

describe('isMarketingPromptRouteExcluded', () => {
  it.each(['/entrar', '/entrar/', '/a', '/a/', '/finalizar', '/finalizar/endereco', '/pedido/NB-123', '/pedido/NB-123/pagamento'])(
    'keeps the sheet away from %s',
    path => {
      expect(isMarketingPromptRouteExcluded(path)).toBe(true)
    }
  )

  it.each(['/', '/menu', '/sacola', '/conta', '/conta/preferencias', '/produto/croissant', '/pedidos'])(
    'lets it open on %s',
    path => {
      expect(isMarketingPromptRouteExcluded(path)).toBe(false)
    }
  )
})

describe('beta 05/11: erros do login com o título certo e no lugar certo', () => {
  it('LOJA-03: conflito de identidade não herda "Código não confere" do campo code', () => {
    const view = authErrorView({ status: 400, field: 'code', errorCode: 'identity_conflict', detail: 'Este número aparece em mais de um cadastro.' }, 'x')
    expect(view.kind).toBe('identity_conflict')
    expect(view.title).toBe('Não conseguimos entrar com este número')
    expect(authErrorOffersSupport(view)).toBe(true)
  })

  it('LOJA-03: código errado continua dizendo que o código não confere', () => {
    const view = authErrorView({ status: 400, field: 'code', detail: 'Código incorreto.' }, 'x')
    expect(view.title).toBe('Código não confere')
    expect(authErrorOffersSupport(view)).toBe(false)
  })

  it('LOJA-04: telefone inválido mora junto do campo', () => {
    expect(authErrorBelongsToPhoneField(authErrorView({ field: 'phone' }, 'x'))).toBe(true)
    expect(authErrorBelongsToPhoneField(authErrorView({ field: 'code' }, 'x'))).toBe(false)
    expect(authErrorBelongsToPhoneField(null)).toBe(false)
  })
})


describe('beta 06/11: o código morto e a espera entre envios dizem a verdade', () => {
  it('SMS-07: tentativas esgotadas não viram "Código não confere"', () => {
    const view = authErrorView({ status: 400, field: 'code', errorCode: 'code_max_attempts', detail: 'Você errou o código 5 vezes, e ele deixou de valer. Peça um novo código.' }, 'x')
    expect(view.kind).toBe('code_dead')
    expect(view.title).toBe('Peça um novo código')
    expect(authErrorKillsCode(view)).toBe(true)
  })

  it('SMS-07: código vencido também libera o reenvio', () => {
    const view = authErrorView({ status: 400, field: 'code', errorCode: 'code_expired', detail: 'Este código não vale mais.' }, 'x')
    expect(authErrorKillsCode(view)).toBe(true)
  })

  it('SMS-07: código errado com tentativas sobrando não mata o código', () => {
    expect(authErrorKillsCode(authErrorView({ status: 400, field: 'code' }, 'x'))).toBe(false)
  })

  it('SMS-08: espera entre envios é "Aguarde um instante", não "Algo não deu certo"', () => {
    expect(authErrorView({ status: 400, errorCode: 'cooldown' }, 'x').title).toBe('Aguarde um instante')
    expect(authErrorView({ status: 429, errorCode: 'cooldown' }, 'x').kind).toBe('rate_limit')
  })

  it('SMS-08: a recusa com código válido leva ao passo do código com o relógio do servidor', () => {
    const now = Date.parse('2026-11-06T05:15:00Z')
    const pending = pendingCodeFromCooldown({
      error_code: 'cooldown',
      phone: '+5543991117788',
      retry_after_seconds: 45,
      code_expires_at: '2026-11-06T05:24:00Z',
      delivery_method: 'sms',
      delivery_label: 'SMS'
    }, now)
    expect(pending).toEqual({
      phone: '+5543991117788',
      deliveryMethod: 'sms',
      deliveryLabel: 'SMS',
      codeExpiresAt: '2026-11-06T05:24:00Z',
      lastSentAtMs: now,
      resendWindowMs: 45_000
    })
    expect(resendCooldown(pending!.lastSentAtMs, now + 1000, pending!.resendWindowMs)).toEqual({ ready: false, remainingSeconds: 44 })
  })

  it('SMS-08: sem código válido não há passo para onde voltar', () => {
    const now = Date.parse('2026-11-06T05:15:00Z')
    expect(pendingCodeFromCooldown({ error_code: 'cooldown', phone: '+5543991117788', retry_after_seconds: 45, code_expires_at: '' }, now)).toBeNull()
    expect(pendingCodeFromCooldown({ error_code: 'rate_limit', phone: '+5543991117788', code_expires_at: '2026-11-06T05:24:00Z' }, now)).toBeNull()
  })

  it('SMS-08: o passo do código volta do recarregamento enquanto o código vale', () => {
    const stored = JSON.stringify({ phone: '+5543991117788', deliveryMethod: 'sms', deliveryLabel: 'SMS', codeExpiresAt: '2026-11-06T05:24:00Z', lastSentAtMs: 1, resendWindowMs: 60_000 })
    expect(restorePendingCode(stored, Date.parse('2026-11-06T05:20:00Z'))?.phone).toBe('+5543991117788')
    expect(restorePendingCode(stored, Date.parse('2026-11-06T05:24:01Z'))).toBeNull()
    expect(restorePendingCode('{quebrado', 0)).toBeNull()
    expect(restorePendingCode(null, 0)).toBeNull()
  })

})
