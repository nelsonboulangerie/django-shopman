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

/**
 * Formatação apenas. Não converte para gramas, não aplica ceiling e não
 * calcula tolerância: o número operacional pertence ao projection do servidor.
 */
export function projectedQuantityDisplay(display: string): string {
  const match = KG_DISPLAY.exec(display);
  if (!match) return display;
  const kilograms = parseLocalizedNumber(match[1] ?? "");
  if (kilograms === null) return display;
  return `${new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  }).format(kilograms)} kg`;
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
      annotation: ingredient.annotation || "",
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

/** Linha da balança no cartão do preparo. */
export interface WeighingRow {
  key: string;
  sku: string;
  name: string;
  target: string;
  annotation: string;
  isOldDough: boolean;
}

interface WeighingRowsTicket {
  output_sku: string;
  ingredients: Array<{
    sku: string;
    name: string;
    target_display?: string;
    quantity_display: string;
    annotation: string;
  }>;
  old_dough?: {
    old_dough_display: string;
    lines: Array<{ sku: string; target_display: string }>;
  } | null;
}

/**
 * As linhas que o padeiro pesa. Sem massa velha, a ficha do preparo (mistura
 * final + partes prontas). Com massa velha, a variante no teto que o servidor
 * já calculou (`final_mix_at_cap`): a massa velha primeiro, e cada insumo no
 * alvo encolhido. A ajuda de contagem ("≈ 7 ovos") é do peso cheio e sai.
 */
export function weighingRows(
  ticket: WeighingRowsTicket,
  withOldDough: boolean,
): WeighingRow[] {
  const oldDough = withOldDough ? ticket.old_dough : null;
  const atCap = new Map(
    (oldDough?.lines ?? []).map((line) => [line.sku, line.target_display]),
  );
  const rows: WeighingRow[] = ticket.ingredients.map((ing) => ({
    key: ing.sku,
    sku: ing.sku,
    name: ing.name,
    target: projectedQuantityDisplay(
      atCap.get(ing.sku) ??
        operationalTargetDisplay(ing.target_display, ing.quantity_display),
    ),
    annotation: oldDough ? "" : ing.annotation,
    isOldDough: false,
  }));
  if (oldDough?.old_dough_display) {
    rows.unshift({
      key: `old-dough-${ticket.output_sku}`,
      sku: ticket.output_sku,
      name: "Massa velha",
      target: projectedQuantityDisplay(oldDough.old_dough_display),
      annotation: "",
      isOldDough: true,
    });
  }
  return rows;
}
