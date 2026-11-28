// Presentation: este dispositivo pode calcular e cobrar? (a resposta `station` do
// `POSView`, a mesma régua das mutações de dinheiro do servidor).
//
// A leitura do quadro escolhe uma gaveta mesmo sem estação, para o balcão não ficar em
// branco; quem recusa é a revisão e o fechamento da venda. Sem este aviso a tela mostrava
// o caixa aberto, deixava montar a comanda e só no Pagamento dizia "Não calculado" e,
// depois, "Vincule este dispositivo a um único terminal ativo". Aqui a tela diz na
// chegada o que falta e oferece vincular.

import type { OperatorScreenAlert } from "../../../operator-kit/app/presentation/screenState";

export interface PosStationReadiness {
  ready: boolean;
  reason: "" | "none" | "ambiguous" | "inactive";
}

const COPY: Record<Exclude<PosStationReadiness["reason"], "">, { title: string; description: string }> = {
  none: {
    title: "Este dispositivo não está vinculado a um caixa.",
    description: "Dá para montar a comanda, mas o total e a cobrança só saem num dispositivo vinculado.",
  },
  ambiguous: {
    title: "Este dispositivo está vinculado a mais de um caixa.",
    description: "O total e a cobrança ficam parados até ele ficar com um caixa só.",
  },
  inactive: {
    title: "Este dispositivo está vinculado a um posto que não é um caixa ativo.",
    description: "Dá para montar a comanda, mas o total e a cobrança só saem num caixa ativo.",
  },
};

/** O aviso da tela (alerts do cabeçalho), ou nada quando o dispositivo pode cobrar. */
export function stationReadinessAlert(
  station: PosStationReadiness | null | undefined,
  onLink: () => void,
): OperatorScreenAlert | null {
  // Sem resposta (servidor antigo, leitura falhou): não acusa o que não sabe.
  if (!station || station.ready || !station.reason) return null;
  const copy = COPY[station.reason];
  return {
    id: `station:${station.reason}`,
    color: "error",
    icon: "i-lucide-monitor-x",
    title: copy.title,
    description: copy.description,
    action: { label: "Vincular a um caixa", onSelect: () => onLink() },
  };
}
