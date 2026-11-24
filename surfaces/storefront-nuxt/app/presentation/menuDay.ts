// EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
// "Para quando?" antes da lista (OC-33 B1, variante B). Aqui só se ESCOLHE a forma
// de dizer o que o servidor decidiu: quais dias valem (`catalog.days`), o que cada
// item tem no dia escolhido (`promise`, já escrito no vocabulário do dia) e para que
// dia é a sacola (`cart.day`). Nenhuma regra de data ou de estoque mora aqui.
import type {
  CartDayProjection,
  CartItemProjection,
  CatalogDaysProjection,
  CatalogItemProjection
} from '~/types/shopman'
import { promiseHour } from '~/presentation/promise'

export interface MenuDayOption {
  value: string
  title: string
  description: string
  disabled: boolean
}

function weekdayShort (value: string): string {
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return ''
  const label = new Intl.DateTimeFormat('pt-BR', { weekday: 'long' }).format(new Date(year, month - 1, day))
  // "quinta-feira" → "Quinta": a forma curta da casa ("quinta, 26/11").
  const word = label.split('-')[0] || label
  return word.charAt(0).toUpperCase() + word.slice(1)
}

function dayMonth (value: string): string {
  const [, month, day] = value.split('-')
  return month && day ? `${day}/${month}` : ''
}

function tomorrowOf (today: string): string {
  const [year, month, day] = today.split('-').map(Number)
  if (!year || !month || !day) return ''
  const next = new Date(year, month - 1, day + 1)
  const mm = `${next.getMonth() + 1}`.padStart(2, '0')
  const dd = `${next.getDate()}`.padStart(2, '0')
  return `${next.getFullYear()}-${mm}-${dd}`
}

/**
 * As opções do "Para quando?": Hoje (apagado quando encerrado ou sem expediente),
 * amanhã e os próximos dias que o servidor diz que a casa atende. "Outro dia" é o
 * calendário, à parte.
 */
export function menuDayOptions (days: CatalogDaysProjection | null | undefined): MenuDayOption[] {
  if (!days) return []
  const tomorrow = tomorrowOf(days.today)
  const options: MenuDayOption[] = [{
    value: days.today,
    title: 'Hoje',
    description: days.today_open ? `${weekdayShort(days.today)}, ${dayMonth(days.today)}` : 'Encerrado',
    disabled: !days.today_open
  }]
  for (const value of days.next_days) {
    options.push({
      value,
      title: value === tomorrow ? 'Amanhã' : weekdayShort(value),
      description: value === tomorrow ? `${weekdayShort(value)}, ${dayMonth(value)}` : dayMonth(value),
      disabled: false
    })
  }
  return options
}

/** O dia escolhido é hoje (o cardápio de sempre, sem data na leitura). */
export function isTodayChoice (days: CatalogDaysProjection | null | undefined, value: string): boolean {
  return !!days && value === days.today
}

/** A data que vai na leitura do cardápio: só dia futuro; hoje é o cardápio de sempre (X13). */
export function menuDayQuery (days: CatalogDaysProjection | null | undefined, value: string): { date?: string } {
  if (!value || isTodayChoice(days, value)) return {}
  return { date: value }
}

/** A barra do cardápio: "Para quinta, 26/11", "Para amanhã, quarta", "Para hoje". */
export function menuDayBarLabel (days: CatalogDaysProjection | null | undefined, value: string): string {
  if (!value) return ''
  if (isTodayChoice(days, value)) return 'Para hoje'
  const selected = days?.selected
  if (selected?.date === value) return `Para ${selected.label}`
  return `Para ${weekdayShort(value).toLowerCase()}, ${dayMonth(value)}`
}

/**
 * O selo do item no cardápio do dia: o servidor já escreveu a frase do dia.
 * Disponível desde a abertura não diz nada (o padrão não se anuncia); depois da
 * abertura, "A partir das 11h". Indisponível é a etiqueta da foto, sem motivo.
 */
export function menuDayItemBadge (
  item: Pick<CatalogItemProjection, 'can_add_to_cart' | 'promise'>
): string {
  if (!item.can_add_to_cart) return ''
  return item.promise?.text || ''
}

/**
 * A linha do alto da sacola datada: "Para quinta, 26/11 · Tudo pronto a partir das
 * 11h". A hora é a do item mais tardio (o pedido só sai inteiro); uma linha sem
 * promessa cala a hora, e a tela não promete o que não sabe.
 */
export function cartDayLine (
  day: CartDayProjection | null | undefined,
  items: ReadonlyArray<Pick<CartItemProjection, 'promise'>> | null | undefined
): { day: string, ready: string } | null {
  if (!day) return null
  let latest = ''
  for (const item of items || []) {
    if (!item.promise || item.promise.date !== day.date) {
      latest = ''
      break
    }
    if (item.promise.ready_at > latest) latest = item.promise.ready_at
  }
  return {
    day: `Para ${day.label}`,
    ready: latest ? `Tudo pronto a partir das ${promiseHour(latest)}` : ''
  }
}

/**
 * O dia em que o cardápio abre na variante B, nesta ordem: o que a cliente acabou
 * de escolher (`?dia=`), o que ficou guardado na aba, o dia da sacola. Sem nenhum,
 * vazio: o cardápio pergunta antes da lista. Dia que o servidor não oferece mais
 * (passou, a casa fechou) não vale.
 */
export function initialMenuDay (
  days: CatalogDaysProjection | null | undefined,
  candidates: ReadonlyArray<string | null | undefined>
): string {
  if (!days) return ''
  for (const value of candidates) {
    if (!value) continue
    if (value === days.today) {
      if (days.today_open) return value
      continue
    }
    if (value > days.today && value <= days.max_date) return value
  }
  return ''
}
