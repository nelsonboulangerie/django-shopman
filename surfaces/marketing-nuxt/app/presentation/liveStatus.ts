// O "ao vivo" ao lado do título (camada visual da suíte, `OperatorLiveStatus`): o
// ponto e a hora da última leitura útil. Só cresce quando a leitura não é ao vivo, e
// aí o estado se escreve por extenso, porque a cor nunca fala sozinha.
//
// Fonte: a conexão da caixa pessoal (`useMarketingNotificationInbox`, SSE que só
// invalida, com poll de 60 s de segurança) e o `generated_at` da leitura da tela.

export type MarketingRealtime = "connecting" | "live" | "polling";

export interface MarketingLiveStatus {
  tone: "live" | "calm" | "late" | "off";
  label: string;
  time: string;
  detail: string;
}

/** "10:03", no fuso da loja. Vazio quando não há leitura. */
export function readTime(instant: string | null | undefined, timeZone: string): string {
  const ms = instant ? Date.parse(instant) : Number.NaN;
  if (!Number.isFinite(ms)) return "";
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(ms));
}

export function marketingLiveStatus(input: {
  realtime: MarketingRealtime;
  /** A última leitura falhou (a tela mostra a anterior, ou nada). */
  failed: boolean;
  generatedAt: string | null | undefined;
  timeZone: string;
}): MarketingLiveStatus {
  const time = readTime(input.generatedAt, input.timeZone);
  if (input.failed) {
    return {
      tone: "off",
      label: "Sem conexão",
      time,
      detail: time
        ? `A tela mostra a leitura das ${time}. Atualize antes de concluir.`
        : "A leitura não chegou. Atualize antes de concluir.",
    };
  }
  if (input.realtime === "polling") {
    return {
      tone: "calm",
      label: "Atualiza sozinho a cada 1 min",
      time,
      detail: "O aviso imediato caiu; a tela confere sozinha a cada minuto.",
    };
  }
  return {
    tone: "live",
    label: "Ao vivo",
    time,
    detail: "A tela muda sozinha quando algo muda.",
  };
}
