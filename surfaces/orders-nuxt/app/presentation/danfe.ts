// A DANFE da NFC-e no card do Gestor — a que vai na sacola da entrega.
//
// Quem decide é o servidor (`backstage/services/order_danfe.py`): a nota existe
// (`danfe_printable`), já saiu (`danfe_printed`), deve sair sozinha agora
// (`danfe_auto_print`). Esta camada só traduz isso em linha de card e escolhe
// quais pedidos a estação deve imprimir sem ninguém pedir.
import type { OrderCardProjection, TwoZoneQueueProjection } from "~/types/orders";

type DanfeFields = Pick<OrderCardProjection, "ref" | "danfe_printable" | "danfe_printed" | "danfe_auto_print">;

export interface DanfeLine {
  /** O fato, à vista: a DANFE já saiu ou ainda não. */
  status: string;
  /** O gesto do botão. */
  action: string;
}

/** A linha da DANFE no card, ou `null` quando não há nota (ou é iFood). */
export function danfeLine(card: DanfeFields): DanfeLine | null {
  if (!card.danfe_printable) return null;
  if (card.danfe_printed) return { status: "DANFE impressa", action: "Reimprimir DANFE" };
  if (card.danfe_auto_print) return { status: "DANFE saindo para a sacola", action: "Imprimir DANFE" };
  return { status: "DANFE não impressa", action: "Imprimir DANFE" };
}

/**
 * Os pedidos cuja DANFE esta estação deve imprimir AGORA, sem ninguém pedir.
 *
 * `attempted` são os que esta aba já tentou: uma tentativa por pedido por aba.
 * Se o papel não sair, o operador fica sabendo pelo aviso e reimprime no card —
 * repetir sozinho a cada leitura do quadro encheria a bobina de REIMPRESSÃO.
 */
export function danfeAutoPrintRefs(
  queue: TwoZoneQueueProjection | null | undefined,
  attempted: ReadonlySet<string>,
): string[] {
  if (!queue) return [];
  const cards: DanfeFields[] = [
    ...queue.expedition_delivery_transit,
    ...queue.expedition_delivery,
    ...queue.expedition_pickup,
  ];
  return [...new Set(cards.filter((card) => card.danfe_auto_print).map((card) => card.ref))]
    .filter((ref) => !attempted.has(ref));
}
