// A DANFE da NFC-e no card do Gestor, a que vai na sacola da entrega.
//
// Quem decide é o servidor (`backstage/services/order_danfe.py`): a DANFE da
// entrega sai sozinha pela impressora do despacho, e o card só acompanha. Esta
// camada traduz o estado em linha de card: o fato, o motivo quando não saiu e
// o gesto do botão.
import type { OrderCardProjection } from "~/types/orders";

type DanfeFields = Pick<
  OrderCardProjection,
  "ref" | "danfe_printable" | "danfe_printed" | "danfe_state" | "danfe_problem"
>;

export interface DanfeLine {
  /** O fato, à vista. */
  status: string;
  /** Por que não saiu e o que fazer. Vazio quando está tudo certo. */
  problem: string;
  /** O gesto do botão. */
  action: string;
  /** A DANFE está na fila da impressora: o botão espera, para não sair duas. */
  sending: boolean;
  /** Não saiu e precisa de alguém. */
  attention: boolean;
}

/** A linha da DANFE no card, ou `null` quando não há nota (ou é iFood). */
export function danfeLine(card: DanfeFields): DanfeLine | null {
  if (!card.danfe_printable) return null;
  const action = card.danfe_printed ? "Reimprimir DANFE" : "Imprimir DANFE";
  const line = (status: string, extra: Partial<DanfeLine> = {}): DanfeLine => ({
    status,
    problem: "",
    action,
    sending: false,
    attention: false,
    ...extra,
  });
  switch (card.danfe_state) {
    case "printed":
      return line("DANFE impressa", { action: "Reimprimir DANFE" });
    case "sending":
      return line("DANFE saindo na impressora", { sending: true });
    case "not_printed":
      return line("DANFE não impressa", { problem: card.danfe_problem || "", attention: true });
    case "on_dispatch":
      return line("A DANFE sai sozinha quando a entrega sair");
    default:
      return line("DANFE disponível");
  }
}
