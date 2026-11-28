/**
 * O mapa único da cor do tempo nas superfícies de operação.
 *
 * A cor responde a uma pergunta semântica, não ao nome que cada API usa:
 * atraso é vermelho, proximidade do prazo é âmbar, dentro do prazo é neutro e
 * verde pertence somente ao estado Pronto. O consumidor continua responsável
 * por traduzir seu contrato real de prazo para um destes estados.
 */
export type TimeState = "late" | "warning" | "on_time" | "ready";
export type TimeTone = "late" | "warning" | "neutral" | "ready";

export function timeTone(state: "ready"): "ready";
export function timeTone(
  state?: Exclude<TimeState, "ready">,
): Exclude<TimeTone, "ready">;
export function timeTone(state: TimeState = "on_time"): TimeTone {
  if (state === "ready") return "ready";
  if (state === "late") return "late";
  if (state === "warning") return "warning";
  return "neutral";
}
