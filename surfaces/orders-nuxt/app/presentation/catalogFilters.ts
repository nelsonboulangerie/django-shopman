// Recorte da matriz por dimensões (FilterBar) — puro e determinístico.
//
// A lista é paginada e filtrada no SERVIDOR: cada dimensão daqui vira uma chave
// da query (ver `useCatalogMatrix`), e as contagens vêm prontas do servidor
// (`CatalogFacets`). Este módulo só descreve as dimensões e lê o recorte da URL.
import type {
  ActiveFilters,
  FilterDimension,
} from "../../../operator-kit/app/types/filters";
import type { CatalogFacets, SurfaceProjection } from "~/types/catalog";

// Ids das dimensões — chaves em inglês, rótulos em pt-BR (convenção do projeto).
export const FILTER_SYNC = "sync_status";
export const FILTER_SURFACE = "surface";
export const FILTER_PUBLISHED = "is_published";
export const FILTER_SELLABLE = "is_sellable";
export const FILTER_STOCK = "stock";
export const FILTER_PIM = "pim_complete";
export const FILTER_VOCATION = "has_vocation";

// ── envio (produto × plataforma) ────────────────────────────────────────────────
// "never" = alvo de projeção que nunca recebeu push (sync_status vazio na célula).
export type SyncBucket = "synced" | "pending" | "error" | "never";

const SYNC_OPTIONS: { value: SyncBucket; label: string }[] = [
  { value: "synced", label: "Sincronizado" },
  { value: "pending", label: "Sincronizando" },
  { value: "error", label: "Com erro" },
  { value: "never", label: "Nunca enviado" },
];

// ── estoque ────────────────────────────────────────────────────────────────────
// Um balde por linha (o produto está num estado só), do pior ao melhor.
export type StockBucket = "out" | "low" | "ok";

const STOCK_OPTIONS: { value: StockBucket; label: string }[] = [
  { value: "ok", label: "Em estoque" },
  { value: "low", label: "Estoque baixo" },
  { value: "out", label: "Esgotado" },
];

// ── dimensões ──────────────────────────────────────────────────────────────────
/**
 * Dimensões oferecidas no catálogo. NÃO inclui coleção: essa é o eixo primário e
 * vive nas pills. Envio e PIM só aparecem quando há alguma plataforma que projeta
 * (sem iFood/Meta/Google ligado, não há o que sincronizar nem feed a completar).
 *
 * As contagens de estoque e envio vêm do SERVIDOR, do recorte inteiro: contar
 * sobre a página seria a mentira que tirou as facetas do painel. Sem `facets`
 * (primeira carga) a opção sai sem contagem, nunca com zero inventado.
 */
export function serverCatalogDimensions(
  surfaces: SurfaceProjection[],
  facets?: CatalogFacets,
): FilterDimension[] {
  const hasTargets = surfaces.some((s) => s.is_projection_target);
  const dimensions: FilterDimension[] = [];

  if (hasTargets) {
    dimensions.push({
      id: FILTER_SYNC,
      label: "Status de envio",
      type: "multi-select",
      options: SYNC_OPTIONS.map((option) => ({
        value: option.value,
        label: option.label,
        count: facets?.sync_status[option.value],
      })),
    });
  }

  dimensions.push({
    id: FILTER_SURFACE,
    label: "Canal ou feed",
    type: "multi-select",
    options: surfaces.map((s) => ({ value: s.ref, label: s.name })),
  });

  dimensions.push(
    { id: FILTER_PUBLISHED, label: "Exibido", type: "boolean", options: [] },
    { id: FILTER_SELLABLE, label: "À venda", type: "boolean", options: [] },
    {
      id: FILTER_STOCK,
      label: "Estoque",
      type: "multi-select",
      options: STOCK_OPTIONS.map((option) => ({
        value: option.value,
        label: option.label,
        count: facets?.stock[option.value],
      })),
    },
  );

  if (hasTargets) {
    dimensions.push({
      id: FILTER_PIM,
      label: "Dados sociais completos",
      type: "boolean",
      options: [],
    });
  }

  // Vocação (só para o B.I.): o "Classificar" do aviso da lista liga este recorte.
  dimensions.push({
    id: FILTER_VOCATION,
    label: "Com vocação",
    type: "boolean",
    options: [],
  });

  return dimensions;
}

/**
 * O recorte do "Classificar": à venda e sem vocação — o mesmo critério do aviso
 * (`vocation_pending` no servidor). Substitui os filtros: herdar um recorte
 * anterior esconderia parte dos produtos que o aviso acabou de contar.
 */
export function vocationPendingFilters(): ActiveFilters {
  return { [FILTER_SELLABLE]: ["true"], [FILTER_VOCATION]: ["false"] };
}

// ── recorte vindo da URL ───────────────────────────────────────────────────────
// O checklist de um canal manda para cá já recortado ("3 produtos recusados pelo
// iFood → Ver e corrigir" abre `/catalog?surface=ifood&sync=error`). Só entram os
// valores que a dimensão conhece: parâmetro torto não vira filtro que zera a tela.
const QUERY_DIMENSIONS: Record<
  string,
  { id: string; values?: readonly string[] }
> = {
  surface: { id: FILTER_SURFACE },
  // Na URL a chave é `sync` (contrato do checklist); a dimensão é `sync_status`.
  sync: { id: FILTER_SYNC, values: SYNC_OPTIONS.map((o) => o.value) },
  stock: { id: FILTER_STOCK, values: STOCK_OPTIONS.map((o) => o.value) },
  pim_complete: { id: FILTER_PIM, values: ["true", "false"] },
  is_published: { id: FILTER_PUBLISHED, values: ["true", "false"] },
  is_sellable: { id: FILTER_SELLABLE, values: ["true", "false"] },
  has_vocation: { id: FILTER_VOCATION, values: ["true", "false"] },
};

export function filtersFromQuery(
  query: Record<string, unknown>,
): ActiveFilters {
  const filters: ActiveFilters = {};
  for (const [param, { id, values }] of Object.entries(QUERY_DIMENSIONS)) {
    const raw = query[param];
    const picked = (Array.isArray(raw) ? raw : [raw])
      .flatMap((value) => (typeof value === "string" ? value.split(",") : []))
      .map((value) => value.trim())
      .filter((value) => value && (!values || values.includes(value)));
    if (picked.length) filters[id] = [...new Set(picked)];
  }
  return filters;
}
