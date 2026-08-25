// Presentation — catalog shaping for the Sale Workspace grid.
//
// Pure transforms over the catalog Projection: ordering the category rail,
// filtering the product grid, and the calm tile fallback visual. No price or
// availability arithmetic — those are sealed in the Projection (price_display)
// and only rendered here.

import type { POSCollectionProjection, POSProductProjection } from "~/types/pos";

/** Favourites first (Projection-driven), then alphabetical (pt-BR). */
export function orderCollections(
  collections: POSCollectionProjection[],
  favoriteRefs: Iterable<string>,
): POSCollectionProjection[] {
  const favorites = new Set(favoriteRefs);
  return [...collections].sort((a, b) => {
    const aFavorite = favorites.has(a.ref) ? 0 : 1;
    const bFavorite = favorites.has(b.ref) ? 0 : 1;
    return aFavorite - bFavorite || a.name.localeCompare(b.name, "pt-BR");
  });
}

/**
 * Normalização de busca: minúsculas SEM diacríticos, para "pao" achar
 * "Pão de Queijo" — o operador digita rápido e sem acento no balcão.
 */
export function normalizeSearchText(value: string): string {
  return (value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

/** O match começa no início de alguma palavra do texto? ("que" em "pão de queijo") */
function matchesWordStart(normalizedText: string, normalizedQuery: string): boolean {
  if (normalizedText.startsWith(normalizedQuery)) return true;
  return normalizedText.includes(` ${normalizedQuery}`);
}

/**
 * Filter the grid by active collection and a free-text query (name or product
 * code), accent-insensitive. Matches at the START of a word rank first — typing
 * "pa" should surface "Pão…" before anything that merely contains "pa".
 */
export function filterProducts(
  products: POSProductProjection[],
  options: { collectionRef?: string; query?: string } = {},
): POSProductProjection[] {
  const collectionRef = options.collectionRef || "";
  const normalized = normalizeSearchText((options.query || "").trim());
  const wordStart: POSProductProjection[] = [];
  const contains: POSProductProjection[] = [];
  for (const product of products) {
    if (collectionRef && product.collection_ref !== collectionRef) continue;
    if (!normalized) {
      wordStart.push(product);
      continue;
    }
    const name = normalizeSearchText(product.name);
    const sku = normalizeSearchText(product.sku);
    if (matchesWordStart(name, normalized) || sku.startsWith(normalized)) {
      wordStart.push(product);
    } else if (name.includes(normalized) || sku.includes(normalized)) {
      contains.push(product);
    }
  }
  return wordStart.concat(contains);
}

/**
 * Deterministic, calm hue for products without a photo — derived from the
 * collection ref so a whole collection shares a family tint (Odoo-style colour
 * coding), kept low-saturation so the grid stays calm, not marketing.
 */
export function productFallbackHue(product: POSProductProjection): number {
  const seed = product.collection_ref || product.sku || product.name;
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) % 360;
  }
  return hash;
}

/**
 * O visual do tile sem foto sai como custom properties (par claro + par
 * escuro); quem escolhe o par é o CSS (`.pos-tile-fallback` × `.dark`) — o
 * gradiente claro fixo estourava no dark mode.
 */
export function productFallbackStyle(product: POSProductProjection): Record<string, string> {
  const hue = productFallbackHue(product);
  const hueTo = (hue + 24) % 360;
  return {
    "--tile-from": `hsl(${hue} 42% 92%)`,
    "--tile-to": `hsl(${hueTo} 38% 85%)`,
    "--tile-from-dark": `hsl(${hue} 24% 26%)`,
    "--tile-to-dark": `hsl(${hueTo} 22% 20%)`,
  };
}

export function productMonogram(product: POSProductProjection): string {
  return (product.name?.trim()?.[0] || "·").toUpperCase();
}
