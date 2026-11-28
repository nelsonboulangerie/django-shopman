// Presentation — a falta de insumo, na frase da bancada (WP-F11).
//
// "Falta 300 g de manteiga": o quanto primeiro, na medida da bancada (o servidor
// manda `shortage_display` já em gramas, a mesma régua do aviso da sugestão no
// Planejamento), depois o quê. Nunca o SKU cru, nunca "0,3 kg".
import type { ProductionMaterialShortageItem } from "~/generated/productionContract";

/** "Manteiga sem sal" vira "manteiga sem sal"; "T65" e "UHT" ficam como estão. */
export function lowerFirst(name: string): string {
  const text = name.trim();
  if (text.length < 2) return text.toLowerCase();
  const [first, second] = [text.charAt(0), text.charAt(1)];
  return second === second.toLowerCase() ? first.toLowerCase() + text.slice(1) : text;
}

export function materialShortageLine(
  item: Pick<ProductionMaterialShortageItem, "name" | "sku" | "shortage_display">,
): string {
  return `Falta ${item.shortage_display} de ${lowerFirst(item.name || item.sku)}`;
}
