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
