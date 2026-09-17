// Leitura de capacidade → o que o operador vê no rail. Puro, sem Vue.
//
// A cor sai da comparação com os limites do Admin (atenção/crítico), nunca de um
// número fixo no código; sem leitura ou sem limites, o estado é "sem leitura" —
// neutro e dito com todas as letras.
import type { CapacityLevel, CapacityResponse, CapacityThresholds } from "../types/capacity";

export function capacityPeakPercent(reading: CapacityResponse | null): number | null {
  if (!reading?.available) return null;
  const values = [reading.memory?.percent, reading.cpu?.percent].filter((v): v is number => typeof v === "number");
  return values.length ? Math.max(...values) : null;
}

export function capacityLevel(
  reading: CapacityResponse | null,
  thresholds: CapacityThresholds | null = reading?.thresholds ?? null,
): CapacityLevel {
  const peak = capacityPeakPercent(reading);
  if (peak == null || !thresholds) return "unknown";
  if (peak >= thresholds.critical_percent) return "critical";
  if (peak >= thresholds.attention_percent) return "attention";
  return "normal";
}

export interface CapacityLevelMeta {
  label: string;
  /** Classe do ponto no gatilho (tokens do tema do operador). */
  dot: string;
  /** Classe do texto do estado no detalhe. */
  text: string;
}

export const CAPACITY_LEVEL_META: Record<CapacityLevel, CapacityLevelMeta> = {
  normal: { label: "Normal", dot: "bg-rail-foreground/45", text: "text-muted-foreground" },
  attention: { label: "Atenção", dot: "bg-warning", text: "text-warning" },
  critical: { label: "Crítica", dot: "bg-destructive", text: "text-destructive" },
  unknown: { label: "Sem leitura", dot: "bg-rail-foreground/25", text: "text-muted-foreground" },
};

function percentText(value: number | null | undefined): string {
  return typeof value === "number" ? `${Math.round(value)}%` : "sem leitura";
}

/** "Memória 62% · CPU 18%" — ou a frase de ambiente sem leitura. */
export function capacitySummary(reading: CapacityResponse | null): string {
  if (!reading?.available) return "Este ambiente não informa a capacidade do serviço.";
  return `Memória ${percentText(reading.memory?.percent)} · CPU ${percentText(reading.cpu?.percent)}`;
}

/** "atualizado há 20 s" / "há 3 min" / "agora". */
export function capacityUpdatedAgo(measuredAt: string | null | undefined, nowMs: number): string {
  const at = measuredAt ? Date.parse(measuredAt) : Number.NaN;
  if (!Number.isFinite(at)) return "";
  const seconds = Math.max(0, Math.round((nowMs - at) / 1000));
  if (seconds < 5) return "atualizado agora";
  if (seconds < 60) return `atualizado há ${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `atualizado há ${minutes} min`;
  return `atualizado há ${Math.floor(minutes / 60)} h`;
}

/** Frase de orientação do detalhe — o que o estado significa para quem está no balcão. */
export function capacityGuidance(level: CapacityLevel, thresholds: CapacityThresholds | null): string {
  switch (level) {
    case "normal":
      return "Há folga para o movimento.";
    case "attention":
      return "Perto do limite: as telas podem ficar lentas no pico.";
    case "critical":
      return thresholds
        ? `No limite: as telas podem travar. Se continuar por ${thresholds.sustain_minutes} min, o gestor é avisado.`
        : "No limite: as telas podem travar.";
    default:
      return "";
  }
}

export function capacityThresholdsText(thresholds: CapacityThresholds | null): string {
  if (!thresholds) return "";
  return `Atenção a partir de ${thresholds.attention_percent}% · crítico a partir de ${thresholds.critical_percent}%`;
}

/** Rótulo acessível do gatilho: estado + números, sem depender da cor. */
export function capacityAriaLabel(reading: CapacityResponse | null, level: CapacityLevel): string {
  const meta = CAPACITY_LEVEL_META[level];
  if (level === "unknown") return `Capacidade do serviço: ${meta.label}`;
  return `Capacidade do serviço: ${meta.label} — ${capacitySummary(reading)}`;
}
