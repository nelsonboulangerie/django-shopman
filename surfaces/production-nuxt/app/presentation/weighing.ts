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
