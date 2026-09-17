export type StockNotifyTransientState = 'paused' | 'cancelled'

/**
 * Confirma a última ação na navegação corrente, sem transformar pausa ou
 * cancelamento em estado persistente do catálogo. No próximo SSR/reload a
 * projeção canônica volta a decidir entre "Anotado" e "Me avise".
 *
 * `subscribed` é o sino que o SERVIDOR devolveu fora do botão — hoje, na
 * resposta do coração (favoritar um esgotado pode anotar o aviso). Vale para
 * todo botão daquele SKU nesta navegação, inclusive cards montados de uma
 * projeção anterior ao gesto; a projeção nova volta a mandar quando chega.
 */
export function useStockNotifyTransientState () {
  const states = useState<Record<string, StockNotifyTransientState>>('stock-notify-transient-states', () => ({}))
  const subscribed = useState<Record<string, boolean>>('stock-notify-subscribed-overrides', () => ({}))

  function setStockNotifyState (sku: string, state: StockNotifyTransientState) {
    states.value = { ...states.value, [sku]: state }
  }

  function clearStockNotifyState (sku: string) {
    if (!(sku in states.value)) return
    states.value = Object.fromEntries(
      Object.entries(states.value).filter(([candidate]) => candidate !== sku)
    )
  }

  function setStockNotifySubscribed (sku: string, value: boolean) {
    subscribed.value = { ...subscribed.value, [sku]: value }
  }

  return { states, subscribed, setStockNotifyState, clearStockNotifyState, setStockNotifySubscribed }
}
