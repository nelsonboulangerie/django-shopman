import type { FomoBadgeProjection } from '~/types/shopman'

// Selos de urgência (#2807): o servidor diz o fato (fornada pronta às 14h03,
// promoção até 18h, 3 unidades) e a tela escreve o tempo pelo relógio dela. O
// cardápio passa por cache de borda (até ~60 s) e a aba fica aberta: um "há 12 min"
// escrito no servidor envelheceria parado. Fato vencido não vira selo.

export type FomoBadgeView = {
  type: string
  label: string
  variant: 'success' | 'warning' | 'promotion'
}

// Espelha `presentation/fomo.py`: a fornada é notícia por 60 min; a promoção vira
// contagem nas últimas 4 h.
const FRESH_WINDOW_MINUTES = 60
const PROMO_COUNTDOWN_HOURS = 4

function instant (value: unknown): number | null {
  if (typeof value !== 'string' || !value) return null
  const ms = Date.parse(value)
  return Number.isFinite(ms) ? ms : null
}

function freshLabel (badge: FomoBadgeProjection, now: number): string | null {
  const finished = instant(badge.meta?.finished_at)
  if (finished === null || finished > now) return null
  const minutes = Math.floor((now - finished) / 60_000)
  if (minutes > FRESH_WINDOW_MINUTES) return null
  return minutes < 1 ? 'Fornada pronta agora' : `Fornada pronta há ${minutes} min`
}

function promoLabel (badge: FomoBadgeProjection, now: number): string | null {
  const until = instant(badge.expires_at)
  if (until === null || until <= now) return null
  const hours = Math.floor((until - now) / 3_600_000)
  if (hours > PROMO_COUNTDOWN_HOURS) return null
  return hours < 1 ? 'Promoção acaba em menos de 1h' : `Promoção acaba em ${hours}h`
}

/** Os selos a desenhar agora, na ordem do servidor (do mais urgente), já sem os vencidos. */
export function fomoBadgeViews (badges: ReadonlyArray<FomoBadgeProjection> | null | undefined, now: number): FomoBadgeView[] {
  const views: FomoBadgeView[] = []
  for (const badge of badges || []) {
    if (badge.type === 'fresh') {
      const label = freshLabel(badge, now)
      if (label) views.push({ type: badge.type, label, variant: 'success' })
    } else if (badge.type === 'promo_countdown') {
      const label = promoLabel(badge, now)
      if (label) views.push({ type: badge.type, label, variant: 'promotion' })
    } else if (badge.type === 'low_stock') {
      views.push({ type: badge.type, label: badge.label, variant: 'warning' })
    }
  }
  return views
}

/** O selo de estoque baixo com o número ("Últimas 3 unidades") substitui o genérico. */
export function fomoCoversLowStock (badges: ReadonlyArray<FomoBadgeProjection> | null | undefined): boolean {
  return (badges || []).some(badge => badge.type === 'low_stock')
}
