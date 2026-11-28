// O selo de conexão do cabeçalho da Produção (WP-F15, P1-17): "Ao vivo" só onde é
// verdade. O tom e o texto são os do `OperatorLiveStatus` do kit:
//
//   sem dado nenhum, a leitura falhou   off   "Sem conexão"
//   com dado, a última leitura falhou   late  "Sem atualizar"
//   canal da Produção aberto            live  "Ao vivo"
//   canal fechado ou ainda abrindo      calm  "Atualiza sozinho a cada 30 s"
//
// A tela que não declara o tempo real (`realtime` ausente) segue no "Ao vivo" de
// antes: hoje é só a grade, que tem o canal próprio (`useProductionBoard`) e passa a
// declará-lo pela issue do "Ficou de fora" do WP-F15.
import type { ProductionRealtime } from "~/composables/useProductionLive";
import {
  SCREEN_STATE_RETRY_LABEL,
  type OperatorScreenAlert,
} from "../../../operator-kit/app/presentation/screenState";

export type LiveSealTone = "live" | "calm" | "late" | "off";

export interface LiveSeal {
  tone: LiveSealTone;
  label: string;
  shortLabel: string;
  detail: string;
}

export function productionLiveSeal(opts: {
  stale: boolean;
  offline?: boolean;
  realtime?: ProductionRealtime | null;
  pollMs?: number | null;
}): LiveSeal {
  if (opts.offline) {
    return {
      tone: "off",
      label: "Sem conexão",
      shortLabel: "",
      detail: "A leitura falhou e a tela tenta de novo sozinha.",
    };
  }
  if (opts.stale) {
    return {
      tone: "late",
      label: "Sem atualizar",
      shortLabel: "",
      detail: "A última leitura falhou: a tela mostra o que tinha.",
    };
  }
  if (opts.realtime == null || opts.realtime === "live") {
    return { tone: "live", label: "Ao vivo", shortLabel: "", detail: "" };
  }
  const seconds = Math.round((opts.pollMs ?? 30_000) / 1000);
  return {
    tone: "calm",
    label: `Atualiza sozinho a cada ${seconds} s`,
    shortLabel: `A cada ${seconds} s`,
    detail: "O aviso imediato dos lotes está fora; a tela lê de novo nesse intervalo.",
  };
}

/**
 * O aviso de dado velho (P2-07): a última leitura falhou e a tela segue mostrando a
 * anterior. Mora nos `alerts` do `OperatorPageHeader` (com X, e volta enquanto a causa
 * durar), nunca numa pílula solta, e traz a saída: ler de novo agora.
 */
export function staleReadAlert(
  what: string,
  retry: () => unknown,
  description = "",
): OperatorScreenAlert {
  return {
    id: "stale-read",
    color: "warning",
    icon: "i-lucide-wifi-off",
    title: `Sem atualizar: a tela mostra ${what} da última leitura`,
    ...(description ? { description } : {}),
    action: { label: SCREEN_STATE_RETRY_LABEL, onSelect: () => void retry() },
  };
}
