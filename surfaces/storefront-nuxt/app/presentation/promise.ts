import type { CartItemProjection, PickupStoreProjection, ReadyPromise } from '~/types/shopman'

// A promessa de quando, como a tela a diz (WP-L02). O fato vem do servidor
// (`promise`, WP-L01): dia, hora e frase. Aqui só se ESCOLHE a forma de dizer
// cada pedaço em cada lugar (página, card, botão, checkout). Nada aqui olha o
// relógio do aparelho: "hoje" é o `day_label` que o servidor escreveu. Sem
// promessa, a tela não promete.

/** O dia é hoje, segundo o servidor. */
export function promiseIsToday (promise: ReadyPromise | null | undefined): boolean {
  return promise?.day_label === 'hoje'
}

/** "15:00" → "15h"; "15:30" → "15h30". Mesma forma do formatador da casa. */
export function promiseHour (readyAt: string): string {
  const [hours, minutes] = readyAt.split(':')
  if (!hours) return ''
  const hour = String(Number(hours))
  return minutes && minutes !== '00' ? `${hour}h${minutes}` : `${hour}h`
}

// O dia sem a data: "amanhã, terça" → "amanhã"; "quinta, 19/11" → "quinta".
function dayWord (promise: ReadyPromise): string {
  return promise.day_label.split(',')[0]?.trim() || promise.day_label
}

// "na quinta", "no sábado", "amanhã".
function dayWithArticle (promise: ReadyPromise): string {
  const word = dayWord(promise)
  if (word === 'amanhã' || word === 'hoje') return word
  return word === 'sábado' || word === 'domingo' ? `no ${word}` : `na ${word}`
}

/** O botão: "Adicionar" no que é de hoje; "Encomendar para amanhã" no que não é. */
export function promiseAddLabel (promise: ReadyPromise | null | undefined, fallback = 'Adicionar'): string {
  if (!promise || promiseIsToday(promise)) return fallback
  return `Encomendar para ${dayWord(promise)}`
}

/**
 * O selo curto do card, no lugar do antigo "Lista de espera": o card não cabe a
 * frase inteira. Sobre o produto a loja fala de disponibilidade, não de
 * prontidão (dono, 24/11/2026). Hoje leva a hora ("Disponível a partir das
 * 15h"); outro dia leva só o dia ("Disponível amanhã", "Disponível na
 * quinta"), e a página do produto diz a hora. Disponível agora não tem selo: é
 * o normal.
 */
export function promiseBadgeLabel (promise: ReadyPromise | null | undefined): string {
  if (!promise || promise.kind === 'ready') return ''
  if (promiseIsToday(promise)) return `Disponível a partir das ${promiseHour(promise.ready_at)}`
  return `Disponível ${dayWithArticle(promise)}`
}

/**
 * A frase da promessa na página do produto, ou nada. O estado padrão (disponível
 * agora) não se diz: a tela só fala quando a disponibilidade difere (dono,
 * 24/11/2026). O texto é o do servidor ("Disponível amanhã, quarta, a partir
 * das 7h").
 */
export function productPromiseLine (promise: ReadyPromise | null | undefined): string {
  if (!promise || promise.kind === 'ready') return ''
  return promise.text
}

export type PickupStoreLines = {
  // "Disponível hoje na Nelson Boulangerie" | "Indisponível hoje na Nelson Boulangerie"
  availability: string
  availableToday: boolean
}

/**
 * Em qual loja o produto está e se está disponível hoje (#2652). É o que o
 * Google exige para "disponibilidade na loja": o nome da loja e o estado,
 * visíveis ao abrir a página. O endereço completo só é exigido quando a cliente
 * abre os detalhes da loja, e com um endereço só ele era ruído (dono,
 * 24/11/2026): a linha fica curta, sem endereço. Só com promessa: sem ela a
 * tela não afirma nem "hoje" nem "indisponível". Disponível hoje = a promessa é
 * de hoje; a encomenda para outro dia é "Indisponível hoje", e a linha da
 * promessa logo acima diz quando fica disponível.
 */
export function pickupStoreLines (
  promise: ReadyPromise | null | undefined,
  store: PickupStoreProjection | null | undefined
): PickupStoreLines | null {
  if (!promise || !store?.name) return null
  const availableToday = promiseIsToday(promise)
  return {
    availability: `${availableToday ? 'Disponível' : 'Indisponível'} hoje na ${store.name}`,
    availableToday
  }
}

/** Depois de pôr na sacola, a página repete o dia: "1 na sacola, para amanhã, terça." */
export function inCartWhenLine (qty: number, promise: ReadyPromise | null | undefined): string {
  if (qty <= 0 || !promise || promiseIsToday(promise)) return ''
  return `${qty} na sacola, para ${promise.day_label}.`
}

// A promessa que manda no pedido: a do item mais tardio (o pedido só fica
// pronto inteiro). Uma linha sem promessa (indisponível ou sem dado) cala tudo:
// a tela não promete o que não sabe.
function latestPromise (
  items: ReadonlyArray<Pick<CartItemProjection, 'promise'>> | null | undefined
): ReadyPromise | null {
  if (!items?.length) return null
  let latest: ReadyPromise | null = null
  for (const item of items) {
    const promise = item.promise
    if (!promise) return null
    if (!latest || promise.date > latest.date || (promise.date === latest.date && promise.ready_at > latest.ready_at)) {
      latest = promise
    }
  }
  return latest
}

/**
 * A promessa na LINHA da sacola: só a de fornada, que é fato do item
 * ("Disponível amanhã, terça, a partir das 15h"). Disponível agora é o normal e não tem
 * frase. A encomenda (o item é de hoje, mas a casa já não tem horário hoje) é
 * fato da casa, igual para todas as linhas: quem diz é `cartReadyLine`, uma
 * vez, no alto da sacola.
 */
export function cartLinePromise (promise: ReadyPromise | null | undefined): string {
  if (!promise || promise.kind !== 'batch') return ''
  return promise.text
}

/**
 * Para quando fica o PEDIDO, no alto da sacola (antes de a cliente escolher
 * retirada ou entrega). Tudo pronto agora não tem frase: é o normal. Com a
 * casa fechada, com o corte do dia ou com um item de fornada, a frase diz o
 * dia e a hora antes do checkout.
 */
export function cartReadyLine (
  items: ReadonlyArray<Pick<CartItemProjection, 'promise'>> | null | undefined
): string {
  const latest = latestPromise(items)
  if (!latest) return ''
  if (promiseIsToday(latest)) {
    return latest.kind === 'ready' ? '' : `Seu pedido fica pronto hoje, a partir das ${promiseHour(latest.ready_at)}.`
  }
  return `Seu pedido fica pronto ${latest.day_label}, a partir das ${promiseHour(latest.ready_at)}.`
}

/**
 * Quando o PEDIDO fica pronto para retirada, no checkout: o item mais tardio
 * manda (o pedido só sai inteiro). Uma linha sem promessa (indisponível ou sem
 * dado) cala a frase: a tela não promete o que não sabe.
 */
export function orderReadyLine (
  items: ReadonlyArray<Pick<CartItemProjection, 'promise'>> | null | undefined
): string {
  const latest = latestPromise(items)
  if (!latest) return ''
  if (latest.kind === 'ready' && promiseIsToday(latest)) return 'Seu pedido fica pronto para retirada hoje.'
  if (promiseIsToday(latest)) return `Seu pedido fica pronto para retirada hoje, a partir das ${promiseHour(latest.ready_at)}.`
  return `Seu pedido fica pronto para retirada ${latest.day_label}, a partir das ${promiseHour(latest.ready_at)}.`
}
