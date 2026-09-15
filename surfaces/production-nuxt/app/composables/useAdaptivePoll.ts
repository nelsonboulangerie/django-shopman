// Adaptive, visibility-aware polling. One place for the app's refresh cadence:
//   - interval() is re-read every tick, so the caller can speed up under
//     pressure (live floor: 30s → 10s while something is late);
//   - a hidden tab skips the fetch (tablet parked on another app costs zero);
//   - coming back to the tab refreshes immediately (no stale first paint).
// Polling over SSE is deliberate for production: the floor clock moves in
// minutes, alerts are low-frequency, and the SSE channel infra is order-scoped
// today — revisit post-alpha if cadence ever tightens (decision: WP-PE4).
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
