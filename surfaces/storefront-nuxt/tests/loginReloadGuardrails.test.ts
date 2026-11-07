import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// O passo do login morava só na memória de /entrar: recarregar perdia o passo do
// código e o do nome (beta 06/11, SMS-08 e SMS-16). Estas travas leem a página,
// que não tem harness de montagem, e conferem que os passos são guardados e
// restaurados pelo mesmo caminho.
const login = readFileSync(fileURLToPath(new URL('../app/pages/entrar.vue', import.meta.url)), 'utf8')

function body (name: string): string {
  const start = login.indexOf(`function ${name} (`)
  expect(start, `função ${name} existe em entrar.vue`).toBeGreaterThan(-1)
  const ends = [login.indexOf('\nfunction ', start + 1), login.indexOf('\nasync function ', start + 1)].filter(i => i > -1)
  return login.slice(start, ends.length ? Math.min(...ends) : undefined)
}

const mounted = login.slice(login.indexOf('onMounted('), login.indexOf('function readStored'))

describe('beta 06/11: /entrar sobrevive ao recarregamento', () => {
  it('SMS-16: entrar no passo do nome deixa a marca; terminar ou pular apaga', () => {
    expect(body('enterWelcomeGate')).toContain('writeStored(WELCOME_PENDING_STORAGE_KEY')
    expect(body('enterWelcomeGateFromSession')).toContain('writeStored(WELCOME_PENDING_STORAGE_KEY')
    expect(body('submitWelcome')).toContain('forgetStored(WELCOME_PENDING_STORAGE_KEY)')
    expect(body('skipWelcome')).toContain('forgetStored(WELCOME_PENDING_STORAGE_KEY)')
  })

  it('SMS-16: com a marca, a montagem pergunta à sessão em vez de mostrar o login', () => {
    expect(mounted).toContain('readStored(WELCOME_PENDING_STORAGE_KEY)')
    expect(mounted).toMatch(/\(welcomeRequested\.value \|\| welcomeWasPending\)/)
    expect(mounted).toContain('enterWelcomeGateFromSession()')
  })

  it('SMS-16: a marca sozinha, com sessão sem nome pendente, não tira o logado do login', () => {
    // Quem abre /entrar já logado quer ver o login; uma marca
    // velha não pode mandá-lo de volta ao destino. Só o convite `?welcome=1` segue.
    const afterWelcome = mounted.slice(mounted.indexOf('if (auth.requires_welcome)'))
    const nav = afterWelcome.indexOf('await navigateTo(nextUrl.value)')
    expect(nav).toBeGreaterThan(-1)
    expect(afterWelcome.slice(0, nav)).toContain('if (welcomeRequested.value) {')
  })

  it('SMS-08: todo envio do código passa por applyPendingCode, que guarda o passo', () => {
    expect(body('applyCodeDelivery')).toContain('applyPendingCode(')
    expect(body('applyPendingCode')).toContain('writeStored(PENDING_CODE_STORAGE_KEY')
    expect(mounted).toContain('restorePendingCode(readStored(PENDING_CODE_STORAGE_KEY)')
  })

  it('SMS-08: a recusa por espera, no pedir e no reenviar, volta ao passo do código', () => {
    expect(body('requestCode')).toContain('applyCooldown(e)')
    expect(body('resendCode')).toContain('applyCooldown(e)')
  })

  it('SMS-07: erro no código limpa os dígitos e, com o código morto, solta o Reenviar', () => {
    const verify = body('verifyCode')
    expect(verify).toContain('codeDigits.value = []')
    expect(verify).toContain('authErrorKillsCode(error.value)')
    expect(verify).toContain("codeExpiresAt.value = ''")
    expect(verify).toContain('lastSentAtMs.value = null')
  })

  it('SMS-09: o prazo da confiança não é escrito à mão na página', () => {
    expect(login).not.toMatch(/\d+ dias/)
    expect(login).not.toMatch(/\d+ meses/)
  })
})
