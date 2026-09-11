import {
  buildMarketingVital,
  reportMarketingVital,
  type MarketingVitalName,
} from "../utils/marketingTelemetry";

type LayoutShiftEntry = PerformanceEntry & { hadRecentInput?: boolean; value?: number };
type InteractionEntry = PerformanceEntry & { duration?: number; interactionId?: number };

export default defineNuxtPlugin(() => {
  if (!("PerformanceObserver" in window)) return;

  const values: Partial<Record<MarketingVitalName, number>> = {};
  const observers: PerformanceObserver[] = [];
  let flushed = false;

  const observe = (type: string, callback: (entries: PerformanceEntryList) => void) => {
    if (!PerformanceObserver.supportedEntryTypes.includes(type)) return;
    const observer = new PerformanceObserver((list) => callback(list.getEntries()));
    observer.observe({ type, buffered: true });
    observers.push(observer);
  };

  observe("largest-contentful-paint", (entries) => {
    const last = entries.at(-1);
    if (last) values.LCP = last.startTime;
  });
  observe("layout-shift", (entries) => {
    values.CLS = entries.reduce((total, raw) => {
      const entry = raw as LayoutShiftEntry;
      return total + (entry.hadRecentInput ? 0 : (entry.value ?? 0));
    }, values.CLS ?? 0);
  });
  observe("event", (entries) => {
    for (const raw of entries) {
      const entry = raw as InteractionEntry;
      if ((entry.interactionId ?? 0) > 0) {
        values.INP = Math.max(values.INP ?? 0, entry.duration ?? 0);
      }
    }
  });

  const flush = () => {
    if (flushed) return;
    flushed = true;
    const pathname = window.location.pathname;
    const dark = document.documentElement.classList.contains("dark");
    for (const name of ["LCP", "INP", "CLS"] as const) {
      const value = values[name];
      if (value == null) continue;
      const sample = buildMarketingVital(name, value, pathname, dark);
      if (sample) void reportMarketingVital(sample);
    }
    for (const observer of observers) observer.disconnect();
  };

  window.addEventListener("pagehide", flush, { once: true });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush();
  }, { once: true });
  window.setTimeout(flush, 15_000);
});
