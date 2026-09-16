// Transforms puros do fluxo de entrada por OTP: máquina de passos
// (telefone → código → boas-vindas), normalização de erros da API de auth
// (rate limit é recuperação calma, não falha) e cooldown de reenvio.

export type AuthStep = 'phone' | 'code' | 'welcome'

export interface AuthFlowState {
  requestedPhone: string
  verified: boolean
  requiresWelcome: boolean
}

export function authStep (state: AuthFlowState): AuthStep {
  if (state.verified && state.requiresWelcome) return 'welcome'
  return state.requestedPhone ? 'code' : 'phone'
}

export type AuthErrorKind = 'rate_limit' | 'invalid_phone' | 'invalid_code' | 'generic'

export interface AuthErrorView {
  kind: AuthErrorKind
  title: string
  message: string
}

const ERROR_TITLES: Record<AuthErrorKind, string> = {
  rate_limit: 'Aguarde um instante',
  invalid_phone: 'Revise o telefone',
  invalid_code: 'Código não confere',
  generic: 'Algo não deu certo'
}

export interface AuthErrorInput {
  status?: number | null
  detail?: string | null
  field?: string | null
}

export function authErrorView (input: AuthErrorInput, fallback: string): AuthErrorView {
  const message = (input.detail || '').trim() || fallback
  let kind: AuthErrorKind = 'generic'
  if (input.status === 429) kind = 'rate_limit'
  else if (input.field === 'phone') kind = 'invalid_phone'
  else if (input.field === 'code') kind = 'invalid_code'
  return { kind, title: ERROR_TITLES[kind], message }
}

export const RESEND_COOLDOWN_MS = 30_000

export interface ResendState {
  ready: boolean
  remainingSeconds: number
}

export function resendCooldown (lastSentAtMs: number | null, nowMs: number): ResendState {
  if (lastSentAtMs == null) return { ready: true, remainingSeconds: 0 }
  const remainingMs = lastSentAtMs + RESEND_COOLDOWN_MS - nowMs
  if (remainingMs <= 0) return { ready: true, remainingSeconds: 0 }
  return { ready: false, remainingSeconds: Math.ceil(remainingMs / 1000) }
}

// A frase inteira sai daqui, montada, e não de pedaços no template: o espaço
// que separava o canal de "para" ficava em fim de nó de texto e o compilador do
// Vue o descartava, então a tela dizia "enviado por SMSpara (43) ...".
export function codeSentPrefix (deliveryLabel: string | null | undefined): string {
  const canal = (deliveryLabel || '').trim()
  return canal ? `Código enviado por ${canal} para` : 'Código enviado para'
}

export function welcomeNameValue (raw: string): string {
  return raw.replace(/\s+/g, ' ').trim()
}

// ── A pergunta de novidades no gate de boas-vindas ─────────────────────────
//
// O gate abre por duas perguntas independentes (`welcome_asks_name`,
// `welcome_asks_marketing`); a tela mostra só o que falta. A caixa de novidades
// nasce DESLIGADA — consentimento de marketing é manifestação afirmativa (LGPD
// art. 8 §4), nunca vem embutido nem pré-marcado. Ligada, ela pede a data de
// nascimento, porque novidades só vão para maiores de 18 e a data é o que prova.

export interface WelcomeGateInput {
  asksName: boolean
  asksMarketing: boolean
  name: string
  marketingOptIn: boolean
  birthday: string
}

// `YYYY-MM-DD` válido, nem no futuro nem antes de 1900; qualquer outra coisa é ''.
export function welcomeBirthdayValue (raw: string, today: Date = new Date()): string {
  const value = (raw || '').trim()
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return ''
  const [, y, m, d] = match
  const year = Number(y)
  const month = Number(m)
  const day = Number(d)
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== day) return ''
  if (year < 1900) return ''
  const todayIso = new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()))
  if (parsed.getTime() > todayIso.getTime()) return ''
  return value
}

export function welcomeCanContinue (input: WelcomeGateInput, today: Date = new Date()): boolean {
  if (input.asksName && !welcomeNameValue(input.name)) return false
  if (input.asksMarketing && input.marketingOptIn && !welcomeBirthdayValue(input.birthday, today)) return false
  return true
}

// O que vai no PATCH do perfil: o nome quando foi pedido, o aniversário quando a
// caixa está ligada. `null` = não há o que gravar no perfil (só a resposta).
export function welcomeProfilePatch (input: WelcomeGateInput, today: Date = new Date()): { first_name?: string, birthday?: string } | null {
  const patch: { first_name?: string, birthday?: string } = {}
  if (input.asksName) {
    const name = welcomeNameValue(input.name)
    if (name) patch.first_name = name
  }
  if (input.asksMarketing && input.marketingOptIn) {
    const birthday = welcomeBirthdayValue(input.birthday, today)
    if (birthday) patch.birthday = birthday
  }
  return Object.keys(patch).length ? patch : null
}

// Aterrissagem do access link (a.vue): quem entra por link e ainda precisa
// confirmar o nome passa pelo passo de boas-vindas ANTES do destino — o mesmo
// passo do fluxo OTP, com o destino preservado em `next` para depois do
// confirmar. Sem boas-vindas pendentes, o destino do servidor vale direto.
export function accessLinkLanding (redirect: string, requiresWelcome: boolean): string {
  const destination = redirect || '/'
  if (!requiresWelcome) return destination
  // Destino que já é a tela de entrada não é re-embrulhado (evita next aninhado
  // quando o mesmo caminho atravessa o handoff de navegador e volta para cá).
  if (destination.startsWith('/entrar')) return destination
  return `/entrar?welcome=1&next=${encodeURIComponent(destination)}`
}

export function otpValidUntilDisplay (expiresAtIso: string | null | undefined): string {
  if (!expiresAtIso?.trim()) return ''
  const parsed = Date.parse(expiresAtIso)
  if (Number.isNaN(parsed)) return ''
  return new Date(parsed).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}
