// Transforms puros do fluxo de entrada por OTP: máquina de passos
// (telefone → código → boas-vindas, que é SÓ o nome), normalização de erros da
// API de auth (rate limit é recuperação calma, não falha) e cooldown de reenvio.

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

export type AuthErrorKind = 'rate_limit' | 'invalid_phone' | 'invalid_code' | 'code_dead' | 'identity_conflict' | 'generic'

export interface AuthErrorView {
  kind: AuthErrorKind
  title: string
  message: string
}

const ERROR_TITLES: Record<AuthErrorKind, string> = {
  rate_limit: 'Aguarde um instante',
  invalid_phone: 'Revise o telefone',
  invalid_code: 'Código não confere',
  // O código estava CERTO: o número é que tem mais de um cadastro. "Código não
  // confere" mentia sobre o que a pessoa digitou (beta 05/11, LOJA-03).
  identity_conflict: 'Não conseguimos entrar com este número',
  // O código venceu ou acabaram as tentativas: não há o que corrigir no que foi
  // digitado. "Código não confere" dizia o contrário (beta 06/11, SMS-07).
  code_dead: 'Peça um novo código',
  generic: 'Algo não deu certo'
}

// Códigos do servidor que dizem que o código enviado não vale mais.
const DEAD_CODE_ERRORS = new Set(['code_max_attempts', 'code_expired'])

export interface AuthErrorInput {
  status?: number | null
  detail?: string | null
  field?: string | null
  errorCode?: string | null
}

export function authErrorView (input: AuthErrorInput, fallback: string): AuthErrorView {
  const message = (input.detail || '').trim() || fallback
  let kind: AuthErrorKind = 'generic'
  // A espera entre envios (`cooldown`) é recuperação calma, com o tempo dito, e
  // não "Algo não deu certo" (beta 06/11, SMS-08).
  if (input.status === 429 || input.errorCode === 'cooldown') kind = 'rate_limit'
  else if (input.errorCode === 'identity_conflict') kind = 'identity_conflict'
  else if (input.errorCode && DEAD_CODE_ERRORS.has(input.errorCode)) kind = 'code_dead'
  else if (input.field === 'phone') kind = 'invalid_phone'
  else if (input.field === 'code') kind = 'invalid_code'
  return { kind, title: ERROR_TITLES[kind], message }
}

/** O erro de telefone mora junto do campo, não no topo da página (beta 05/11, LOJA-04). */
export function authErrorBelongsToPhoneField (error: AuthErrorView | null | undefined): boolean {
  return error?.kind === 'invalid_phone'
}

/** Conflito de identidade: a saída é falar com a loja, e o botão mora no próprio aviso. */
export function authErrorOffersSupport (error: AuthErrorView | null | undefined): boolean {
  return error?.kind === 'identity_conflict'
}

/** O código morreu: a tela esconde a validade, limpa os dígitos e libera o "Reenviar". */
export function authErrorKillsCode (error: AuthErrorView | null | undefined): boolean {
  return error?.kind === 'code_dead'
}

export const LOCAL_PHONE_ERROR = 'Informe o DDD e o número, como (43) 99999-9999.'

// A espera do "Reenviar" é a do SERVIDOR (`resend_after_seconds`, o gate G11 do
// doorman). Eram 30 s cravados aqui contra 60 s cobrados lá: o botão liberava e
// o servidor recusava. Este número é só o fallback, igual ao default do doorman,
// para resposta antiga sem o campo.
export const RESEND_COOLDOWN_MS = 60_000

export function resendWindowMs (resendAfterSeconds: number | null | undefined): number {
  return typeof resendAfterSeconds === 'number' && Number.isFinite(resendAfterSeconds) && resendAfterSeconds >= 0
    ? resendAfterSeconds * 1000
    : RESEND_COOLDOWN_MS
}

export interface ResendState {
  ready: boolean
  remainingSeconds: number
}

export function resendCooldown (lastSentAtMs: number | null, nowMs: number, windowMs: number = RESEND_COOLDOWN_MS): ResendState {
  if (lastSentAtMs == null) return { ready: true, remainingSeconds: 0 }
  const remainingMs = lastSentAtMs + windowMs - nowMs
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

// O que o passo do nome grava no perfil. O campo é UM, e a sugestão que vem
// do servidor é o nome inteiro ("Pablo Valentini"): mandar tudo em
// `first_name` desfazia a divisão feita na entrada e, com o sobrenome já
// gravado, a tela passava a dizer "Pablo Valentini Valentini". A regra é a da
// casa (`shopman.utils.names.split_full_name`): primeiro token é o nome, o
// resto é o sobrenome. Um nome só ("Talita") não manda `last_name`, para não
// apagar o sobrenome que já está no cadastro.
export function welcomeNameFields (raw: string): { first_name: string, last_name?: string } {
  const [firstName = '', ...rest] = welcomeNameValue(raw).split(' ')
  const lastName = rest.join(' ')
  return lastName ? { first_name: firstName, last_name: lastName } : { first_name: firstName }
}

// ── A declaração de maioridade, feita ao ENTRAR ────────────────────────────
//
// A nota ao lado do botão de entrar, em TODOS os caminhos (telefone/código,
// aparelho reconhecido, access link): continuar confirma ser maior de idade e
// aceita os Termos de uso. O servidor carimba o cadastro em toda autenticação
// (`adult_declaration`, versão `login-terms-pt-BR-v1`); é essa a prova que o
// marketing direto lê. A frase é FIXA, não copy configurável: a versão do lado
// do servidor representa exatamente esta frase (o teste de contrato lê este
// arquivo). Nunca "18", "anos" nem "adulto" — é "maior de idade".
export const LOGIN_ADULT_DECLARATION_LEAD = 'Ao continuar, você confirma que é maior de idade e aceita os'
export const LOGIN_TERMS_LINK_LABEL = 'Termos de uso'
export const LOGIN_ADULT_DECLARATION = `${LOGIN_ADULT_DECLARATION_LEAD} ${LOGIN_TERMS_LINK_LABEL}.`

// ── O convite de novidades NÃO é passo do login ────────────────────────────
//
// A pergunta "avisos pelo WhatsApp?" sobe como bottom sheet (MarketingPromptSheet)
// na página em que a pessoa cai depois de entrar — não é pré-condição nem
// bloqueia nada. Ela nunca interrompe o que a pessoa veio fazer: fica fora das
// portas de entrada (/entrar, /a), do checkout e do pedido (pagamento e
// acompanhamento). A chave nasce DESLIGADA — consentimento de marketing é
// manifestação afirmativa (LGPD art. 8 §4), nunca pré-marcado.
export function isMarketingPromptRouteExcluded (path: string): boolean {
  return path === '/entrar' || path.startsWith('/entrar/')
    || path === '/a' || path.startsWith('/a/')
    || path === '/finalizar' || path.startsWith('/finalizar/')
    || path === '/pedido' || path.startsWith('/pedido/')
}

// Aterrissagem do access link (a.vue): quem entra por link e ainda precisa
// confirmar o NOME passa pelo passo de boas-vindas ANTES do destino — o mesmo
// passo do fluxo OTP, com o destino preservado em `next` para depois do
// confirmar. Sem nome pendente, o destino do servidor vale direto (o convite de
// novidades não passa por aqui: é sheet na página de destino).
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

// ── O passo do código sobrevive ao recarregamento ──────────────────────────
//
// Quem pede o código por SMS sai para o app de mensagens, e o navegador pode
// descartar a aba. Ao voltar, a página recarregava no passo do telefone, o
// pedido novo esbarrava na espera do servidor e o código que já tinha chegado
// não tinha onde ser digitado (beta 06/11, SMS-08). O passo fica guardado na
// sessão do navegador enquanto o código vale; nunca o código, só o envio.
export const PENDING_CODE_STORAGE_KEY = 'shopman.login.pending-code'

export interface PendingCode {
  phone: string
  deliveryMethod: string
  deliveryLabel: string
  codeExpiresAt: string
  lastSentAtMs: number
  resendWindowMs: number
}

export function restorePendingCode (raw: string | null | undefined, nowMs: number): PendingCode | null {
  if (!raw) return null
  let parsed: Partial<PendingCode>
  try {
    parsed = JSON.parse(raw) as Partial<PendingCode>
  } catch {
    return null
  }
  if (!parsed || typeof parsed.phone !== 'string' || !parsed.phone) return null
  if (typeof parsed.codeExpiresAt !== 'string') return null
  const expiresAt = Date.parse(parsed.codeExpiresAt)
  // Código vencido não volta: o passo dele já não leva a lugar nenhum.
  if (Number.isNaN(expiresAt) || expiresAt <= nowMs) return null
  if (typeof parsed.lastSentAtMs !== 'number' || typeof parsed.resendWindowMs !== 'number') return null
  return {
    phone: parsed.phone,
    deliveryMethod: typeof parsed.deliveryMethod === 'string' ? parsed.deliveryMethod : '',
    deliveryLabel: typeof parsed.deliveryLabel === 'string' ? parsed.deliveryLabel : '',
    codeExpiresAt: parsed.codeExpiresAt,
    lastSentAtMs: parsed.lastSentAtMs,
    resendWindowMs: parsed.resendWindowMs
  }
}

// A recusa da espera entre envios (G11) traz o código que ainda vale: com ela a
// tela volta ao passo do código, com o "Reenviar" no tempo que o servidor cobra.
// Sem código válido (`code_expires_at` vazio), não há passo para onde voltar.
export function pendingCodeFromCooldown (data: Record<string, unknown> | null | undefined, nowMs: number): PendingCode | null {
  if (!data || data.error_code !== 'cooldown') return null
  const phone = typeof data.phone === 'string' ? data.phone : ''
  const codeExpiresAt = typeof data.code_expires_at === 'string' ? data.code_expires_at : ''
  if (!phone || !codeExpiresAt) return null
  const retryAfter = typeof data.retry_after_seconds === 'number' ? data.retry_after_seconds : 0
  return restorePendingCode(JSON.stringify({
    phone,
    deliveryMethod: data.delivery_method,
    deliveryLabel: data.delivery_label,
    codeExpiresAt,
    lastSentAtMs: nowMs,
    resendWindowMs: Math.max(0, retryAfter) * 1000
  }), nowMs)
}

// O passo do nome também sobrevive ao recarregamento: a sessão já está aberta e
// o servidor ainda diz `requires_welcome`, mas o passo morava só na memória da
// página, e o recarregar mostrava o login a quem já tinha entrado (beta 06/11,
// SMS-16). A marca só diz "este navegador estava no passo do nome"; quem decide
// se o passo ainda vale é a sessão do servidor.
export const WELCOME_PENDING_STORAGE_KEY = 'shopman.login.welcome-pending'
