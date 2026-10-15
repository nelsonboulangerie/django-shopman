import type { PublicStatusLevel, PublicStatusSnapshot } from "../types/status";

export const STATUS_COPY: Record<PublicStatusLevel, { label: string; detail: string; icon: string }> = {
  operational: { label: "Tudo funcionando", detail: "Os serviços estão operando normalmente.", icon: "i-lucide-circle-check" },
  degraded: { label: "Desempenho reduzido", detail: "Um ou mais serviços apresentam lentidão.", icon: "i-lucide-gauge" },
  outage: { label: "Interrupção de serviço", detail: "Um ou mais serviços estão indisponíveis.", icon: "i-lucide-triangle-alert" },
  maintenance: { label: "Manutenção programada", detail: "Uma manutenção está em andamento.", icon: "i-lucide-wrench" },
  unknown: { label: "Verificação indisponível", detail: "Não foi possível confirmar o estado mais recente.", icon: "i-lucide-circle-help" },
};

export const statusIsFresh = (snapshot: PublicStatusSnapshot, now = Date.now(), maxAgeMs = 120_000): boolean => {
  if (!snapshot.observedAt) return false;
  const observedAt = Date.parse(snapshot.observedAt);
  return Number.isFinite(observedAt) && now - observedAt <= maxAgeMs && observedAt <= now + 10_000;
};

export const safeSnapshot = (snapshot: PublicStatusSnapshot, now = Date.now()): PublicStatusSnapshot => {
  if (statusIsFresh(snapshot, now)) return snapshot;
  return {
    ...snapshot,
    overall: "unknown",
    components: snapshot.components.map((component) => ({ ...component, status: "unknown" })),
  };
};
