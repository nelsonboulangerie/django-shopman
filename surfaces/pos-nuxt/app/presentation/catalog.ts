// Presentation — catalog shaping for the Sale Workspace grid.
//
// Pure transforms over the catalog Projection: ordering the category rail,
// filtering the product grid, and the calm tile fallback visual. No price or
// availability arithmetic — those are sealed in the Projection (price_display)
// and only rendered here.

import type { POSCartItem, POSCollectionProjection, POSProductProjection } from "~/types/pos";
import { lineUnits, productBlockedLabel } from "~/presentation/weighed";

/**
 * Quanto DESTE PRODUTO já entrou no pedido — o número do selo no card do grid.
 *
 * ⚠️ SOMA todas as linhas do SKU, e é a única leitura da tela que ainda agrega
 * por produto. A comanda passou a admitir duas linhas do mesmo item (uma já na
 * cozinha, outra recém-lançada); para quem olha o grid, são dois. A pergunta
 * aqui é de catálogo ("quanto deste produto o cliente pediu"), não de linha — e
 * de identidade para agregado se vai sempre.
 */
export function cartQtyForSku(items: POSCartItem[], sku: string): number {
  // Peça pesada conta como UMA no selo (duas peças de queijo = 2, não 0,6 kg).
  return items.reduce((total, item) => (item.sku === sku ? total + lineUnits(item) : total), 0);
}

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
 * Filter the grid by active collection and a free-text query (name, SKU or
 * barcode), accent-insensitive. Matches at the START of a word rank first —
 * typing "pa" should surface "Pão…" before anything that merely contains "pa".
 *
 * ⚠️ O leitor de código de barras do balcão DIGITA aqui: ele é um teclado que
 * manda os dígitos e um Enter. Por isso o GTIN entra no índice, e casa
 * INTEIRO — um código de barras não é prefixo de nada, e casar por pedaço
 * faria a bipada cair no produto errado. O casamento exato vem na frente da
 * fila, para o Enter que o leitor manda em seguida pegar o produto bipado.
 */
export function filterProducts(
  products: POSProductProjection[],
  options: { collectionRef?: string; query?: string } = {},
): POSProductProjection[] {
  const collectionRef = options.collectionRef || "";
  const normalized = normalizeSearchText((options.query || "").trim());
  const exact: POSProductProjection[] = [];
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
    const gtin = normalizeSearchText(product.gtin || "");
    if (gtin && gtin === normalized) {
      exact.push(product);
    } else if (matchesWordStart(name, normalized) || sku.startsWith(normalized)) {
      wordStart.push(product);
    } else if (name.includes(normalized) || sku.includes(normalized)) {
      contains.push(product);
    }
  }
  return exact.concat(wordStart, contains);
}

// ── Ocultar indisponíveis ──────────────────────────────────────────────────
// Preferência de EXIBIÇÃO do dispositivo, não regra de disponibilidade: o
// produto inerte (esgotado ou sem preço, o mesmo critério do selo do tile) sai
// da grade, e só. Padrão = mostrar, porque sumir da grade faz o operador
// procurar um botão que "sumiu"; quem quer a grade enxuta liga no olho.

export const HIDE_UNAVAILABLE_STORAGE_KEY = "pos.hideUnavailable";

/** O produto não pode entrar no pedido agora (mesmo critério do selo do tile). */
export function isUnavailableProduct(
  product: Pick<POSProductProjection, "price_q" | "sold_out" | "sold_out_reason">,
): boolean {
  return Boolean(productBlockedLabel(product));
}

/** Tira os indisponíveis quando `hide` está ligado, e diz quantos saíram. */
export function hideUnavailableProducts(
  products: POSProductProjection[],
  hide: boolean,
): { products: POSProductProjection[]; hiddenCount: number } {
  if (!hide) return { products, hiddenCount: 0 };
  const visible = products.filter((product) => !isUnavailableProduct(product));
  return { products: visible, hiddenCount: products.length - visible.length };
}

/** "1 indisponível oculto" / "3 indisponíveis ocultos". */
export function hiddenUnavailableLabel(count: number): string {
  return count === 1 ? "1 indisponível oculto" : `${count} indisponíveis ocultos`;
}

/** Só "1" liga; qualquer outra coisa (vazio, storage bloqueado) é o padrão: mostrar. */
export function parseHideUnavailable(raw: unknown): boolean {
  return raw === "1";
}

/**
 * O produto que o Enter adiciona a partir da busca: o PRIMEIRO resultado
 * DISPONÍVEL na ordem do filtro (esgotado não entra na comanda — pula). Com um
 * único resultado disponível, é ele. Busca vazia não decide nada: Enter só age
 * sobre uma busca digitada (senão adicionaria o primeiro produto da grade).
 */
export function enterTargetProduct(
  filtered: POSProductProjection[],
  query: string,
): POSProductProjection | null {
  if (!(query || "").trim()) return null;
  return filtered.find((product) => !product.sold_out && product.price_q > 0) ?? null;
}

/**
 * O tile sem foto veste a cor da coleção primária (`collection_color`, hex NB
 * de `Collection.metadata` via Projection) como custom property; o CSS deriva
 * os tints por `color-mix` sobre `--background`/`--foreground` (regra
 * `.pos-tile-fallback` × `.dark`), acompanhando a polaridade do tema. Sem cor
 * configurada não sai property nenhuma — o CSS cai no par neutro do tema.
 */
export function productFallbackStyle(product: POSProductProjection): Record<string, string> {
  const color = (product.collection_color || "").trim();
  return color ? { "--tile-color": color } : {};
}

/**
 * A cor de cada coleção, para o ponto do chip na grade (v4). A coleção não traz cor
 * na Projection; os produtos dela trazem (`collection_color`, a mesma do tile), e a
 * primeira configurada vale. Coleção sem cor fica fora do mapa (o chip cai no neutro).
 */
export function collectionColorMap(products: POSProductProjection[]): Map<string, string> {
  const colors = new Map<string, string>();
  for (const product of products) {
    const ref = product.collection_ref || "";
    const color = (product.collection_color || "").trim();
    if (ref && color && !colors.has(ref)) colors.set(ref, color);
  }
  return colors;
}

/**
 * Ícone Lucide genérico da coleção primária (`collection_icon`, de
 * `Collection.metadata`). Sem ícone configurado, um pacote neutro — calmo,
 * sem fingir saber o que o produto é.
 */
export function productFallbackIcon(product: POSProductProjection): string {
  const icon = (product.collection_icon || "").trim();
  return icon ? `lucide:${icon}` : "lucide:package";
}

// ── Cartão de escolha ──────────────────────────────────────────────────────
// Produtos com o mesmo `choice_group` (dado do Admin, ex.: "Chás da casa") viram
// UM tile na grade, que abre a escolha entre eles. Nada aqui conhece "chá". Cada
// escolha lança o próprio SKU, pelo mesmo `add` de sempre.

export interface POSChoiceGroup {
  name: string;
  options: POSProductProjection[];
  /** "R$ 14,00" quando todas custam o mesmo; "a partir de R$ 14,00" quando não. */
  priceLabel: string;
  /** Inerte só quando NENHUMA opção pode entrar no pedido. */
  allBlocked: boolean;
  /** A foto do tile: a da primeira opção vendável que tem foto. */
  cover: POSProductProjection;
  /** O que se escolhe (`choice_group_label`, ex.: "Sabor"): o título da escolha
   *  no diálogo. "" quando o Admin não deu nome. */
  label: string;
}

export type POSGridEntry =
  | { kind: "product"; key: string; product: POSProductProjection }
  | { kind: "group"; key: string; group: POSChoiceGroup };

function choiceGroupName(product: POSProductProjection): string {
  return (product.choice_group || "").trim();
}

/** Grupos do catálogo inteiro; grupo de uma opção só não é escolha. */
export function choiceGroupsByName(products: POSProductProjection[]): Map<string, POSProductProjection[]> {
  const groups = new Map<string, POSProductProjection[]>();
  for (const product of products) {
    const name = choiceGroupName(product);
    if (!name) continue;
    groups.set(name, [...(groups.get(name) || []), product]);
  }
  for (const [name, members] of groups) {
    if (members.length < 2) groups.delete(name);
  }
  return groups;
}

export function choiceGroup(name: string, options: POSProductProjection[]): POSChoiceGroup {
  const sellable = options.filter((option) => !productBlockedLabel(option));
  const priced = options.filter((option) => option.price_q > 0);
  let priceLabel = "";
  if (priced.length) {
    const cheapest = priced.reduce((min, option) => (option.price_q < min.price_q ? option : min));
    const samePrice = priced.every((option) => option.price_q === cheapest.price_q);
    priceLabel = samePrice ? cheapest.price_display : `a partir de ${cheapest.price_display}`;
  }
  const cover =
    sellable.find((option) => option.image_url?.trim()) ||
    options.find((option) => option.image_url?.trim()) ||
    sellable[0] ||
    options[0]!;
  const label = options.map((option) => (option.choice_group_label || "").trim()).find(Boolean) || "";
  return { name, options, priceLabel, allBlocked: sellable.length === 0, cover, label };
}

/**
 * O que a grade mostra. Com busca digitada, cada produto aparece sozinho: quem
 * digita "camille" (ou bipa um código) quer o produto, e o Enter da busca lança
 * o primeiro resultado. Sem busca, os membros de um grupo saem da grade e um tile
 * do grupo entra no lugar do primeiro; as opções são o grupo inteiro do catálogo,
 * mesmo com uma categoria ativa.
 */
export function gridEntries(
  filtered: POSProductProjection[],
  allProducts: POSProductProjection[],
  query: string,
): POSGridEntry[] {
  const asProducts = filtered.map((product) => ({ kind: "product" as const, key: `product:${product.sku}`, product }));
  if ((query || "").trim()) return asProducts;
  const groups = choiceGroupsByName(allProducts);
  if (!groups.size) return asProducts;
  const entries: POSGridEntry[] = [];
  const placed = new Set<string>();
  for (const product of filtered) {
    const name = choiceGroupName(product);
    const members = name ? groups.get(name) : undefined;
    if (!members) {
      entries.push({ kind: "product", key: `product:${product.sku}`, product });
      continue;
    }
    if (placed.has(name)) continue;
    placed.add(name);
    entries.push({ kind: "group", key: `group:${name}`, group: choiceGroup(name, members) });
  }
  return entries;
}
