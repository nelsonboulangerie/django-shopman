// Timeouts transparentes: helpers puros de contagem regressiva ancorados no
// relógio do servidor. Todo TTL que afeta o cliente (expiração do PIX, deadline
// de confirmação) precisa de countdown vivo. `nowMs` entra por parâmetro para
// manter as funções puras e testáveis (mesmo padrão de cart.ts/holdCountdown).

// Diferença servidor−cliente. A UI alinha seu relógio ao do servidor para que o
// countdown não derrape se o relógio do aparelho estiver errado.
export function serverClockOffsetMs (serverNowIso: string | null | undefined, clientNowMs: number): number {
  if (!serverNowIso) return 0
  const server = Date.parse(serverNowIso)
  if (Number.isNaN(server)) return 0
  return server - clientNowMs
}

export interface DeadlineCountdown {
  totalSeconds: number
  mmss: string
  isExpired: boolean
}

// Contagem mm:ss até o deadline, clampada em zero. Acima de 1h ainda exibe em
// minutos (ex.: 60:00 para o PIX padrão de 1h) — sem horas, por simplicidade.
export function deadlineCountdown (deadlineIso: string | null | undefined, nowMs: number): DeadlineCountdown | null {
  if (!deadlineIso) return null
  const deadline = Date.parse(deadlineIso)
  if (Number.isNaN(deadline)) return null
  const totalSeconds = Math.max(0, Math.floor((deadline - nowMs) / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  const pad = (value: number) => String(value).padStart(2, '0')
  return { totalSeconds, mmss: `${pad(minutes)}:${pad(seconds)}`, isExpired: totalSeconds === 0 }
}

// O tempo que falta dito por extenso: "Faltam 14 min 45 s". Para a contagem que
// vive numa FRASE, ao lado de um horário: "Confirme em 14:45" logo abaixo de
// "até 13h27" se lê como hora do dia, e a tela fica com duas horas que brigam
// (coordenação, 19/11/2026). O `mmss` continua valendo onde o número mora
// sozinho num relógio (a barra do Pix).
export function remainingPhrase (totalSeconds: number): string {
  const total = Math.max(0, Math.floor(totalSeconds))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  if (minutes === 0) return `${seconds === 1 ? 'Falta' : 'Faltam'} ${seconds} s`
  if (minutes === 1 && seconds === 0) return 'Falta 1 min'
  return `Faltam ${minutes} min ${String(seconds).padStart(2, '0')} s`
}

// Percentual restante (0..100) numa janela conhecida. Para a barra do PIX a
// janela é o tempo restante no primeiro render (anchor): a barra drena de cheia
// a vazia honestamente, sem depender do início real do intent (que a projeção
// não expõe).
export function countdownPct (remainingSeconds: number, windowSeconds: number): number {
  if (windowSeconds <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((remainingSeconds / windowSeconds) * 100)))
}

export const URGENT_THRESHOLD_PCT = 20

export function isCountdownUrgent (pct: number): boolean {
  return pct <= URGENT_THRESHOLD_PCT
}
