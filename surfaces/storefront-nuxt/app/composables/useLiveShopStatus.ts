import type { ShopStatusProjection } from '~/types/shopman'

// Loja viva (WP-L04): a casa abre e fecha sem evento nenhum. O servidor manda a
// hora da próxima virada (`opens_at`, `closes_at`, no formato "HH:MM" da loja), e a
// tela relê o estado logo depois dela, sozinha. Quem deixou a aba escondida relê
// na volta (o motivo `visible` do `useLiveStore`, que não segura conexão).
//
// A conta usa o relógio do aparelho como aproximação da hora da loja: a cliente
// está na mesma cidade, e o que decide é sempre a resposta do servidor. Por isso
// são duas releituras, uma logo depois da virada e outra um minuto adiante, para
// o aparelho adiantado não reler cedo demais e ficar com o estado antigo.

/** Folga depois da virada: o servidor vira primeiro, a tela pergunta em seguida. */
export const SHOP_BOUNDARY_GRACE_MS = 5_000
/** Segunda pergunta, para o relógio do aparelho que anda adiantado. */
export const SHOP_BOUNDARY_RETRY_MS = 60_000
const DAY_MS = 24 * 60 * 60 * 1000

/** Milissegundos de `now` até a próxima ocorrência de "HH:MM"; null se ilegível. */
export function msUntilClock (clock: string | null | undefined, now: Date): number | null {
  const match = /^(\d{1,2}):(\d{2})/.exec(String(clock || ''))
  if (!match) return null
  const hours = Number(match[1])
  const minutes = Number(match[2])
  if (hours > 23 || minutes > 59) return null
  const target = new Date(now)
  target.setHours(hours, minutes, 0, 0)
  const delta = target.getTime() - now.getTime()
  return delta > 0 ? delta : delta + DAY_MS
}

/** A próxima virada da casa: fecha se está aberta, abre se está fechada. */
export function nextShopBoundaryMs (
  status: Pick<ShopStatusProjection, 'is_open' | 'opens_at' | 'closes_at'> | null | undefined,
  now: Date
): number | null {
  if (!status) return null
  return msUntilClock(status.is_open ? status.closes_at : status.opens_at, now)
}

export function useLiveShopStatus (
  status: () => ShopStatusProjection | null | undefined,
  refresh: () => unknown
) {
  if (!import.meta.client) return
  let timers: ReturnType<typeof setTimeout>[] = []

  function clear () {
    timers.forEach(timer => clearTimeout(timer))
    timers = []
  }

  function reread () {
    void Promise.resolve(refresh()).catch(() => undefined)
  }

  function arm () {
    clear()
    const wait = nextShopBoundaryMs(status(), new Date())
    if (wait === null) return
    timers = [
      setTimeout(reread, wait + SHOP_BOUNDARY_GRACE_MS),
      setTimeout(reread, wait + SHOP_BOUNDARY_GRACE_MS + SHOP_BOUNDARY_RETRY_MS)
    ]
  }

  watch(() => {
    const current = status()
    return current ? `${current.is_open}|${current.opens_at}|${current.closes_at}` : ''
  }, arm)
  useLiveStore(reread, { causes: ['visible'], minIntervalMs: SHOP_BOUNDARY_RETRY_MS })

  if (getCurrentInstance()) {
    onMounted(arm)
    onBeforeUnmount(clear)
  }
  return { arm, clear }
}
