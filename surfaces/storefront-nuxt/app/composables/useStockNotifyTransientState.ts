export type StockNotifyTransientState = 'paused' | 'cancelled'

/**
 * Confirma a última ação na navegação corrente, sem transformar pausa ou
 * cancelamento em estado persistente do catálogo. No próximo SSR/reload a
 * projeção canônica volta a decidir entre "Anotado" e "Me avise".
 */
export function useStockNotifyTransientState () {
  const states = useState<Record<string, StockNotifyTransientState>>('stock-notify-transient-states', () => ({}))

  function setStockNotifyState (sku: string, state: StockNotifyTransientState) {
    states.value = { ...states.value, [sku]: state }
  }

  function clearStockNotifyState (sku: string) {
    if (!(sku in states.value)) return
    states.value = Object.fromEntries(
      Object.entries(states.value).filter(([candidate]) => candidate !== sku)
    )
  }

  return { states, setStockNotifyState, clearStockNotifyState }
}
