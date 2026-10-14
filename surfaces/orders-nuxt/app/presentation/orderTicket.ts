// A VIA PEDIDO no Gestor: o papel do pedido, à mão de quem cuida da fila.
//
// O papel é o mesmo do PDV (`backstage/services/order_documents.py`, via "order"):
// o servidor compõe os bytes ESC/POS na rota `ticket-escpos` e carimba a primeira
// impressão (`ticket_printed_at`); a próxima sai marcada como 2ª via. Esta camada
// só escreve o item do menu e as frases do resultado.
//
// Sem impressora nesta estação o item continua no menu, apagado e dizendo por quê:
// esconder fazia o operador procurar um gesto que existe (o PDV aprendeu isso com
// a gaveta, `useCounterAgent`).
import type { StationDeviceAgent } from "~/types/orders";

export interface OrderTicketMenuItem {
  label: string;
  icon: string;
  disabled: boolean;
  /** Por que não dá, quando não dá: curto, na linha de baixo do item. */
  description?: string;
  /** O motivo inteiro do servidor e onde a via sai (dica ao parar o ponteiro). */
  title?: string;
}

/** A linha curta do item apagado: o menu não estica para caber o motivo inteiro. */
export const NO_PRINTER_SHORT = "Este dispositivo não tem impressora.";

/** Esta estação manda papel para a bobina? */
export function stationPrints(agent: StationDeviceAgent | null | undefined): boolean {
  return Boolean(agent?.can_print && agent.agent_url);
}

/** A frase de quando esta estação não imprime: o motivo do servidor e onde sai. */
export function noPrinterReason(agent: StationDeviceAgent | null | undefined): string {
  const reason = (agent?.reason || "").trim() || NO_PRINTER_SHORT;
  return `${reason} A Via Pedido sai no dispositivo que tem impressora.`;
}

export function orderTicketMenuItem(
  agent: StationDeviceAgent | null | undefined,
  { printing = false }: { printing?: boolean } = {},
): OrderTicketMenuItem {
  const prints = stationPrints(agent);
  return {
    label: printing ? "Imprimindo a Via Pedido…" : "Imprimir Via Pedido",
    icon: "i-lucide-printer",
    disabled: printing || !prints,
    ...(prints ? {} : { description: NO_PRINTER_SHORT, title: noPrinterReason(agent) }),
  };
}

/** O resultado, dito com o pedido e se saiu como 2ª via. */
export function orderTicketPrintedMessage(ref: string, reprint: boolean): string {
  return reprint
    ? `Via Pedido do pedido ${ref} impressa, marcada como 2ª via.`
    : `Via Pedido do pedido ${ref} impressa.`;
}
