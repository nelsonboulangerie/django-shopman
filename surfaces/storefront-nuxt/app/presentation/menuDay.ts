// EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
// O dia do pedido na variante B (OC-33 B1), na direção visual E2 que o dono escolheu
// (25/11/2026): quem só olha não é interrompido; o primeiro "+" com a casa fechada abre
// a folha "Quando" com o próximo dia já marcado; depois, o dia é a etapa feita do
// checkout ("Quando · qui, 26/11 · Editar"). Aqui só se ESCOLHE a forma de dizer o que o
// servidor decidiu: quais dias valem (`catalog.days`), o que cada item tem no dia
// (`promise`) e para que dia é a sacola (`cart.day`). Nenhuma regra de data ou de
// estoque mora aqui.
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
}

const WEEKDAYS = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado']
const WEEKDAYS_SHORT = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb']

function parts (value: string): [number, number, number] | null {
  const [year, month, day] = value.split('-').map(Number)
  return year && month && day ? [year, month, day] : null
}

function weekdayIndex (value: string): number {
  const p = parts(value)
  return p ? new Date(p[0], p[1] - 1, p[2]).getDay() : -1
}

function dayMonth (value: string): string {
  const p = parts(value)
  return p ? `${String(p[2]).padStart(2, '0')}/${String(p[1]).padStart(2, '0')}` : ''
}

function addDays (value: string, n: number): string {
  const p = parts(value)
  if (!p) return ''
  const next = new Date(p[0], p[1] - 1, p[2] + n)
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}-${String(next.getDate()).padStart(2, '0')}`
}

/** "Quinta, 26/11": o dia por extenso curto, como a opção de data do checkout. */
export function weekdayDayMonth (value: string): string {
  const i = weekdayIndex(value)
  if (i < 0) return ''
  const word = WEEKDAYS[i]!
  return `${word.charAt(0).toUpperCase()}${word.slice(1)}, ${dayMonth(value)}`
}

/** "qui, 26/11": o dia no resumo da etapa feita e no verbo da ação. */
export function shortDayLabel (value: string): string {
  const i = weekdayIndex(value)
  return i < 0 ? '' : `${WEEKDAYS_SHORT[i]}, ${dayMonth(value)}`
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

/**
 * A folha pergunta o dia no primeiro "+"? Só quando a casa já não tem horário hoje
 * (`today_open`, do servidor) e a sacola ainda não tem dia. Com a casa aberta, o "+"
 * põe na sacola de hoje, sem perguntar: o padrão não se anuncia.
 */
export function needsDayBeforeAdd (days: CatalogDaysProjection | null | undefined, chosen: string): boolean {
  return !!days && !chosen && !days.today_open
}

/**
 * As opções rápidas da folha "Quando": hoje (só se ainda dá) e o próximo dia que a casa
 * atende, que vem marcado. "Outra data" é o calendário, à parte.
 */
export function daySheetOptions (days: CatalogDaysProjection | null | undefined): MenuDayOption[] {
  if (!days) return []
  const options: MenuDayOption[] = []
  if (days.today_open) options.push({ value: days.today, title: 'Hoje', description: weekdayDayMonth(days.today) })
  const next = days.next_days[0]
  if (next) {
    const tomorrow = next === addDays(days.today, 1)
    options.push({ value: next, title: tomorrow ? 'Amanhã' : 'Próxima fornada', description: weekdayDayMonth(next) })
  }
  return options
}

/** O dia que a folha já traz marcado: o escolhido, ou o próximo que a casa atende. */
export function suggestedDay (days: CatalogDaysProjection | null | undefined, chosen: string): string {
  if (chosen) return chosen
  return days?.next_days[0] || ''
}

/** O verbo com o dia: "Encomendar para amanhã", "Encomendar para qui, 26/11", "Pedir para hoje". */
export function dayActionLabel (days: CatalogDaysProjection | null | undefined, value: string): string {
  if (!days || !value) return 'Escolher o dia'
  if (value === days.today) return 'Pedir para hoje'
  if (value === addDays(days.today, 1)) return 'Encomendar para amanhã'
  return `Encomendar para ${shortDayLabel(value)}`
}

/** A etapa feita "Quando" aparece com dia escolhido que não é hoje. */
export function showsDayStep (days: CatalogDaysProjection | null | undefined, chosen: string): boolean {
  return !!chosen && !isTodayChoice(days, chosen)
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

function latestReadyAt (
  day: CartDayProjection,
  items: ReadonlyArray<Pick<CartItemProjection, 'promise'>> | null | undefined
): string {
  let latest = ''
  for (const item of items || []) {
    if (!item.promise || item.promise.date !== day.date) return ''
    if (item.promise.ready_at > latest) latest = item.promise.ready_at
  }
  return latest
}

/**
 * O PEDIDO da sacola datada, dito uma vez no alto: "Tudo pronto a partir das 15h" (a
 * hora do item mais tardio; o pedido só sai inteiro). Uma linha sem promessa cala a
 * hora: a tela não promete o que não sabe. O dia mora na etapa feita, não aqui.
 */
export function cartDayReadyLine (
  day: CartDayProjection | null | undefined,
  items: ReadonlyArray<Pick<CartItemProjection, 'promise'>> | null | undefined
): string {
  if (!day) return ''
  const latest = latestReadyAt(day, items)
  return latest ? `Tudo pronto a partir das ${promiseHour(latest)}` : ''
}

/**
 * A linha do ITEM na sacola datada: só a hora, e só quando ela difere da do pedido
 * ("Tudo pronto a partir das 15h" já cobre a igual). Voz de produto: "Disponível…".
 */
export function cartDayItemLine (
  day: CartDayProjection | null | undefined,
  items: ReadonlyArray<Pick<CartItemProjection, 'promise'>> | null | undefined,
  item: Pick<CartItemProjection, 'promise'>
): string {
  if (!day || !item.promise || item.promise.date !== day.date) return ''
  const latest = latestReadyAt(day, items)
  if (!latest || item.promise.ready_at === latest) return ''
  return `Disponível a partir das ${promiseHour(item.promise.ready_at)}`
}

/**
 * O dia em que o cardápio abre na variante B: o que veio na URL (`?dia=`), o guardado
 * na aba, o dia da sacola. Dia que o servidor não oferece mais (passou, a casa fechou)
 * não vale; sem nenhum, vazio, e o cardápio é o de sempre.
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
