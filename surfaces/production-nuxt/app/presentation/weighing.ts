import type {
  ProductionBlindLabel,
  ProductionLabelPrintDocument,
  ProductionPreparationLabelTicket,
} from "~/types/productionPrinting";

const KG_DISPLAY = /^\s*([+-]?[\d.,]+)\s*kg\s*$/i;

function parseLocalizedNumber(raw: string): number | null {
  const value = raw.trim();
  if (!value) return null;
  const normalized = value.includes(",")
    ? value.replace(/\./g, "").replace(",", ".")
    : value;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Espaço não separável: o número e a unidade andam juntos ("7200 g", nunca "7200 / g"). */
const NBSP = "\u00a0";
const NUMBER_THEN_UNIT = /(\d)[ \t]+(?=[^\d\s])/g;

/** Prende cada número à palavra que vem logo depois dele ("7200 g", "≈ 0,132 litros"). */
export function keepNumberWithUnit(text: string | null | undefined): string {
  return (text ?? "").replace(NUMBER_THEN_UNIT, `$1${NBSP}`);
}

/**
 * Formatação apenas. Não converte para gramas, não aplica ceiling e não
 * calcula tolerância: o número operacional pertence ao projection do servidor.
 * O número e a unidade saem presos (#3656): a quantidade quebra inteira, ou não quebra.
 */
export function projectedQuantityDisplay(display: string): string {
  const match = KG_DISPLAY.exec(display);
  const kilograms = match ? parseLocalizedNumber(match[1] ?? "") : null;
  if (kilograms === null) return keepNumberWithUnit(display);
  return `${new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  }).format(kilograms)}${NBSP}kg`;
}

/** `target_display` já vem operacional; quantity é somente fallback transitório. */
export function operationalTargetDisplay(
  targetDisplay: string | undefined,
  compatibleQuantityDisplay = "",
): string {
  return projectedQuantityDisplay(targetDisplay || compatibleQuantityDisplay);
}

/** Converte somente o documento sanitizado do job em props do renderer HTML. */
export function blindLabelsFromPrintDocument(
  document: ProductionLabelPrintDocument,
): ProductionBlindLabel[] {
  if (document.mode !== "blind") return [];
  return document.tickets.flatMap((ticket, ticketIndex) =>
    (ticket.ingredients ?? []).map((ingredient, ingredientIndex) => ({
      code: ticket.blind_code,
      ingredient: ingredient.name,
      sku: ingredient.sku,
      weight: operationalTargetDisplay(
        ingredient.target_display,
        ingredient.quantity_display,
      ),
      annotation: keepNumberWithUnit(ingredient.annotation),
      date: ticket.made_display || document.selected_date,
      key: `${ticket.ticket_ref}-${ingredient.sku}-${ticketIndex}-${ingredientIndex}`,
    })),
  );
}

export function preparationLabelsFromPrintDocument(
  document: ProductionLabelPrintDocument,
): ProductionPreparationLabelTicket[] {
  if (document.mode !== "explicit") return [];
  return document.tickets.map((ticket) => ({
    ticket_ref: ticket.ticket_ref,
    name: ticket.name ?? "",
    output_sku: ticket.output_sku ?? "",
    output_quantity_display: ticket.output_quantity_display ?? "",
    total_weight_display: ticket.total_weight_display ?? "",
    sources_display: ticket.sources_display ?? "",
    blind_code: ticket.blind_code,
    made_display: ticket.made_display,
    expiry_display: ticket.expiry_display ?? "",
  }));
}

/** Linha da balança no cartão do preparo (a mesma que vai para a etiqueta). */
export interface WeighingRow {
  key: string;
  sku: string;
  name: string;
  target: string;
  annotation: string;
  /** A quantidade como o servidor a mostra: é ela que prende a marca de "Separado". */
  quantity: string;
}

interface WeighingRowsTicket {
  ingredients: Array<{
    sku: string;
    name: string;
    target_display?: string;
    quantity_display: string;
    annotation: string;
  }>;
}

/**
 * As linhas que o padeiro pesa: a ficha do preparo como o servidor mandou. A massa
 * velha, quando a ficha usa, é um ingrediente com lote (ADR-027, item 12) e já vem
 * na lista; a tela não monta outra receita.
 */
export function weighingRows(ticket: WeighingRowsTicket): WeighingRow[] {
  return ticket.ingredients.map((ing, index) => ({
    key: `${ing.sku}-${index}`,
    sku: ing.sku,
    name: ing.name,
    target: operationalTargetDisplay(ing.target_display, ing.quantity_display),
    annotation: keepNumberWithUnit(ing.annotation),
    quantity: ing.quantity_display,
  }));
}

interface WeighingLabelTicket extends WeighingRowsTicket {
  blind_code: string;
}

/**
 * As etiquetas cegas da prévia, linha a linha da balança: o papel e a tela saem da
 * mesma função (P1-26), e não há como uma pesar outra receita.
 */
export function weighingLabels<T extends WeighingLabelTicket>(
  tickets: readonly T[],
  identity: (ticket: T) => string,
  dateDisplay: string,
): ProductionBlindLabel[] {
  return tickets.flatMap((ticket) =>
    weighingRows(ticket).map((row) => ({
      code: ticket.blind_code,
      ingredient: row.name,
      sku: row.sku,
      weight: row.target,
      annotation: row.annotation,
      date: dateDisplay,
      key: `${identity(ticket)}-${row.key}`,
    })),
  );
}

interface StockLine {
  is_subrecipe: boolean;
  is_short: boolean;
  available_display: string;
  missing_display: string;
}

/**
 * O saldo e a falta de um insumo na Preparação. Pré-preparo nunca mostra saldo nem
 * falta (decisão de 03/07): ele se faz na hora. A falta diz quanto ("Faltam 300 g"),
 * com o número que o servidor calculou.
 */
export function stockFacts(line: StockLine): { available: string; shortage: string } {
  if (line.is_subrecipe) return { available: "", shortage: "" };
  const available = line.available_display ? projectedQuantityDisplay(line.available_display) : "";
  if (!line.is_short || !line.missing_display) return { available, shortage: "" };
  return { available, shortage: `Faltam ${projectedQuantityDisplay(line.missing_display)}` };
}
