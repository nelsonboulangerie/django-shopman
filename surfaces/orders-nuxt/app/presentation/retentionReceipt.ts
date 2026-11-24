// O RECIBO DO VALOR RETIDO no Gestor (#3538).
//
// Encomenda paga e não retirada: o que a loja retém é multa, com recibo e sem nota
// fiscal (contador, 24/11/2026). O servidor compõe o papel na rota
// `retention-receipt-escpos` e carimba a primeira impressão
// (`retention_receipt_printed_at`); a próxima sai marcada como 2ª via. O recibo sai
// sozinho no fim do gesto do "Não retirado", e o menu do pedido reimprime. Esta
// camada só escreve o item do menu e as frases do resultado.
//
// Sem impressora nesta estação o item continua no menu, apagado e dizendo por quê,
// como a Via Pedido. O cliente tem o mesmo recibo no link do pedido.
import type { StationDeviceAgent } from "~/types/orders";
import { NO_PRINTER_SHORT, stationPrints } from "~/presentation/orderTicket";

export interface RetentionReceiptMenuItem {
  label: string;
  icon: string;
  disabled: boolean;
  description?: string;
  title?: string;
}

/** A frase de quando esta estação não imprime: o motivo do servidor e onde o recibo também está. */
export function retentionNoPrinterReason(agent: StationDeviceAgent | null | undefined): string {
  const reason = (agent?.reason || "").trim() || NO_PRINTER_SHORT;
  return `${reason} O recibo sai no dispositivo que tem impressora, e o cliente também o vê no link do pedido.`;
}

export function retentionReceiptMenuItem(
  agent: StationDeviceAgent | null | undefined,
  { printing = false, printed = false }: { printing?: boolean; printed?: boolean } = {},
): RetentionReceiptMenuItem {
  const prints = stationPrints(agent);
  const label = printing
    ? "Imprimindo o recibo do valor retido…"
    : printed
      ? "Reimprimir recibo do valor retido"
      : "Imprimir recibo do valor retido";
  return {
    label,
    icon: "i-lucide-receipt",
    disabled: printing || !prints,
    ...(prints ? {} : { description: NO_PRINTER_SHORT, title: retentionNoPrinterReason(agent) }),
  };
}

/** O resultado, dito com o pedido e se saiu como 2ª via. */
export function retentionReceiptPrintedMessage(ref: string, reprint: boolean): string {
  return reprint
    ? `Recibo do valor retido do pedido ${ref} impresso, marcado como 2ª via.`
    : `Recibo do valor retido do pedido ${ref} impresso.`;
}
