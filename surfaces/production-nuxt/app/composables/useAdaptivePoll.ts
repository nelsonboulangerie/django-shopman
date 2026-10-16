// Adaptive, visibility-aware polling. One place for the app's refresh cadence:
//   - interval() is re-read every tick, so the caller can speed up under
//     pressure (live floor: 30s → 10s while something is late);
//   - a hidden tab skips the fetch (tablet parked on another app costs zero);
//   - coming back to the tab refreshes immediately (no stale first paint).
// Na grade da Produção (useProductionBoard) este poll é a RESERVA: a mudança
// chega pelo SSE `backstage-production` (ADR-016). Onde ainda não há canal, ele
// é a cadência da tela.
export function useAdaptivePoll(refresh: () => unknown, interval: () => number): void {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;
  let inFlight = false;
  let consecutiveFailures = 0;

  const backoffMultiplier = () => Math.min(2 ** consecutiveFailures, 8);
  const jitteredDelay = () => {
    const delay = Math.max(interval(), 5_000) * backoffMultiplier();
    return delay + Math.floor(delay * 0.2 * Math.random());
  };

  function schedule() {
    if (disposed) return;
    timer = setTimeout(() => {
      timer = null;
      if (document.hidden) {
        schedule();
        return;
      }
      void runCycle();
    }, jitteredDelay());
  }

  async function runCycle() {
    if (disposed || inFlight) return;
    inFlight = true;
    try {
      await refresh();
      consecutiveFailures = 0;
    } catch {
      // Erros continuam visíveis no read-side; o fallback desacelera antes de
      // tentar de novo para não martelar uma rede ou servidor degradado.
      consecutiveFailures += 1;
    } finally {
      inFlight = false;
      schedule();
    }
  }

  function onVisible() {
    if (disposed || document.hidden) return;
    if (timer) clearTimeout(timer);
    timer = null;
    // runCycle absorve a rejeição e rearma o fallback conforme o resultado.
    void runCycle();
  }

  onMounted(() => {
    schedule();
    document.addEventListener("visibilitychange", onVisible);
  });
  onBeforeUnmount(() => {
    disposed = true;
    if (timer) clearTimeout(timer);
    timer = null;
    document.removeEventListener("visibilitychange", onVisible);
  });
}
