// FILIPETAS — o pedido remoto virando papel para o painel de parede.
//
// O dono pediu assim: "poder imprimir uma filipeta, tipo um comprovante de
// pedido remoto, antes do pagamento... para todos os pedidos da semana, por
// exemplo. Assim fica fácil de visualizar em um painel físico."
//
// Aqui mora só o FORMATO e a aritmética do intervalo. Quem decide que pedidos
// entram no lote é o servidor (`/orders/tickets/`), e quem compõe os bytes da
// bobina é o `receipt_escpos` — a tela nunca desenha papel.

import { dateLabel, parseLocalDate } from "./schedule";

/** Uma linha da conferência: o que sairia, sem carimbar nada. */
export interface TicketRow {
  ref: string;
  customer_name: string;
  commitment_date: string;
  window_label: string;
  fulfillment_type: "delivery" | "pickup" | string;
  fulfillment_label: string;
  status: string;
  already_printed: boolean;
}

export interface TicketRange {
  date_from: string;
  date_to: string;
}

/**
 * Os intervalos que a padaria realmente pede.
 *
 * "A semana" é o padrão porque foi o exemplo do dono, e ela começa HOJE, não na
 * segunda: o painel serve para enxergar o que vem pela frente, e um lote que
 * começa três dias atrás imprime filipeta de pedido já entregue.
 */
export type TicketPreset = "today" | "tomorrow" | "week" | "fortnight";

export const PRESET_LABELS: Record<TicketPreset, string> = {
  today: "Hoje",
  tomorrow: "Amanhã",
  week: "Esta semana",
  fortnight: "15 dias",
};

const PRESET_SPAN: Record<TicketPreset, { start: number; end: number }> = {
  today: { start: 0, end: 0 },
  tomorrow: { start: 1, end: 1 },
  week: { start: 0, end: 6 },
  fortnight: { start: 0, end: 14 },
};

/**
 * Acima disto a tela avisa antes do gesto.
 *
 * Não é o teto do lote (esse é do servidor) — é o ponto em que o operador
 * merece saber quanto papel vai andar. Cada filipeta come uns 12 cm de bobina;
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

export function resolveRange(preset: TicketPreset, today: string): TicketRange {
  const span = PRESET_SPAN[preset];
  return { date_from: addDays(today, span.start), date_to: addDays(today, span.end) };
}

/** Qual chip acende para o intervalo atual. `""` = intervalo escolhido à mão. */
export function activePreset(range: TicketRange, today: string): TicketPreset | "" {
  for (const preset of Object.keys(PRESET_SPAN) as TicketPreset[]) {
    const candidate = resolveRange(preset, today);
    if (candidate.date_from === range.date_from && candidate.date_to === range.date_to) return preset;
  }
  return "";
}

/** "Hoje" quando as pontas se encontram; senão "Hoje até sáb, 06/09". */
export function rangeLabel(range: TicketRange, today: string): string {
  const from = dateLabel(range.date_from, today);
  if (range.date_from === range.date_to) return from;
  return `${from} até ${dateLabel(range.date_to, today)}`;
}

/** "34 filipetas" / "1 filipeta" / "nenhuma filipeta". */
export function ticketCountLabel(count: number): string {
  if (count <= 0) return "nenhuma filipeta";
  return count === 1 ? "1 filipeta" : `${count} filipetas`;
}

/** O texto do CTA. O número entra no botão porque é o que ninguém quer errar. */
export function printCtaLabel(count: number): string {
  return count === 1 ? "Imprimir 1 filipeta" : `Imprimir ${count} filipetas`;
}

export interface BatchNotice {
  tone: "neutral" | "warning" | "danger";
  message: string;
}

/**
 * O aviso que precede o gesto — ninguém quer descobrir na bobina que pediu 200.
 *
 * Três estados, não dois: o intervalo vazio não é "erro", é "não há o que
 * imprimir"; e o que passa do teto do servidor é recusa, não conselho.
 */
export function batchNotice(count: number, maxBatch: number): BatchNotice | null {
  if (count <= 0) {
    return { tone: "neutral", message: "Nenhum pedido com compromisso neste intervalo." };
  }
  if (count > maxBatch) {
    return {
      tone: "danger",
      message: `${ticketCountLabel(count)} passam do limite de ${maxBatch} por lote. Escolha um intervalo menor.`,
    };
  }
  if (count >= BATCH_WARN_AT) {
    return {
      tone: "warning",
      message: `${ticketCountLabel(count)} vão sair seguidas na bobina. Confira o intervalo antes.`,
    };
  }
  return null;
}

/** O lote pode ser impresso agora? Vazio e estouro travam o botão. */
export function canPrintBatch(count: number, maxBatch: number): boolean {
  return count > 0 && count <= maxBatch;
}

export interface TicketDayGroup {
  date: string;
  date_label: string;
  rows: TicketRow[];
}

/**
 * A conferência agrupada por DIA, na ordem em que o papel vai sair.
 *
 * O servidor já entrega ordenado por compromisso; agrupar aqui é só dar ao olho
 * a mesma divisão que o painel vai ter na parede. A ordem das linhas dentro do
 * dia é preservada — ela é a ordem da bobina.
 */
export function groupByDate(rows: TicketRow[], today: string): TicketDayGroup[] {
  const groups: TicketDayGroup[] = [];
  for (const row of rows) {
    const last = groups[groups.length - 1];
    if (last && last.date === row.commitment_date) {
      last.rows.push(row);
      continue;
    }
    groups.push({
      date: row.commitment_date,
      date_label: dateLabel(row.commitment_date, today) || row.commitment_date,
      rows: [row],
    });
  }
  return groups;
}

/** O ícone do recebimento. Ícone, nunca emoji. */
export function fulfillmentIcon(type: string): string {
  return type === "delivery" ? "lucide:bike" : "lucide:shopping-bag";
}
