// VIA PEDIDO — o pedido remoto virando papel para o painel de parede.
// O papel é a Via Pedido (`backstage/services/order_documents.py`); o dono achou
// "filipeta" um nome horrível, e "ficha" saiu da tela com a seção Encomendas
// (ENCOMENDAS-PDV-PLAN, WP-E2): na tela o papel se chama "via".
//
// O dono pediu assim: "poder imprimir uma filipeta, tipo um comprovante de
// pedido remoto, antes do pagamento... para todos os pedidos da semana, por
// exemplo. Assim fica fácil de visualizar em um painel físico."
//
// Desde 28/09 o lote não tem tela própria: é o botão "Imprimir N vias" da tela
// das Encomendas, que imprime o que está VISÍVEL (período + filtros). Aqui mora
// só o FORMATO do gesto e a aritmética de datas; quem decide que pedidos entram
// é o servidor (`/orders/tickets/escpos/`), e quem compõe os bytes da bobina é
// o `receipt_escpos` — a tela nunca desenha papel.

import { parseLocalDate } from "./schedule";

export interface TicketRange {
  date_from: string;
  date_to: string;
}

/**
 * Acima disto a tela avisa antes do gesto.
 *
 * Não é o teto do lote (esse é do servidor) — é o ponto em que o operador
 * merece saber quanto papel vai andar. Cada via come uns 12 cm de bobina;
 * 25 delas já são três metros no chão do balcão.
 */
export const BATCH_WARN_AT = 25;

/** "2026-09-04" a partir de um `Date`, no fuso LOCAL. */
export function isoDate(date: Date): string {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

/**
 * Soma dias a uma data ISO, sem passar por UTC.
 *
 * `new Date(iso)` lê a string como UTC e, a oeste de Greenwich, já começa no dia
 * anterior — somar 6 daria cinco dias de intervalo. Ver `schedule.parseLocalDate`.
 */
export function addDays(iso: string, days: number): string {
  const date = parseLocalDate(iso);
  if (!date) return iso;
  date.setDate(date.getDate() + days);
  return isoDate(date);
}

/** "34 vias" / "1 via" / "nenhuma via". */
export function ticketCountLabel(count: number): string {
  if (count <= 0) return "nenhuma via";
  return count === 1 ? "1 via" : `${count} vias`;
}

/**
 * O texto do CTA. O número entra no botão porque é o que ninguém quer errar —
 * e zero não é número de botão: sem via para imprimir, a frase inteira.
 */
export function printCtaLabel(count: number): string {
  if (count <= 0) return "Nenhuma via para imprimir";
  return count === 1 ? "Imprimir 1 via" : `Imprimir ${count} vias`;
}

export interface BatchNotice {
  tone: "warning" | "danger";
  message: string;
}

/**
 * O aviso que precede o gesto — ninguém quer descobrir na bobina que pediu 200.
 *
 * Só quando pede atenção: o lote comum não enche a tela de aviso, e o vazio já
 * está dito no próprio botão. O que passa do teto do servidor é recusa, não
 * conselho.
 */
export function batchNotice(count: number, maxBatch: number): BatchNotice | null {
  if (maxBatch > 0 && count > maxBatch) {
    return {
      tone: "danger",
      message: `${ticketCountLabel(count)} passam do limite de ${maxBatch} por lote. Estreite os filtros ou escolha um dia.`,
    };
  }
  if (count >= BATCH_WARN_AT) {
    return {
      tone: "warning",
      message: `${ticketCountLabel(count)} vão sair seguidas na bobina.`,
    };
  }
  return null;
}

/** O lote pode ser impresso agora? Vazio e estouro travam o botão. */
export function canPrintBatch(count: number, maxBatch: number): boolean {
  return count > 0 && (maxBatch <= 0 || count <= maxBatch);
}

/** O ícone do recebimento. Ícone, nunca emoji. */
export function fulfillmentIcon(type: string): string {
  return type === "delivery" ? "lucide:bike" : "lucide:shopping-bag";
}
