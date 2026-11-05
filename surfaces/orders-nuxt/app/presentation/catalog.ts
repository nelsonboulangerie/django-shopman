// Catalog matrix presentation — pure, deterministic transforms.
// The backend owns availability rules; this layer only groups/filters for display
// and maps semantic cell state → label + functional tone (color only where it means
// something: green = available, amber = paused, muted = absent/unpublished).
import type {
  CatalogRowProjection,
  CellSyncStatus,
  SurfaceCellProjection,
  SurfaceProjection,
  SurfaceSyncStatus,
} from "~/types/catalog";
import { readingCsvMoney, readingCsvText } from "../../../operator-kit/app/presentation/readingChart";

export type CellState =
  | "available"
  | "paused"
  | "unpublished"
  | "archived"
  | "absent";

export interface CellView {
  state: CellState;
  label: string;
  toneClass: string; // tailwind classes for the cell chip
}

// ── client-side search (rows already collection-scoped server-side) ────────────

export function filterRows(
  rows: CatalogRowProjection[],
  query: string,
): CatalogRowProjection[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter(
    (r) =>
      r.name.toLowerCase().includes(q) ||
      r.sku.toLowerCase().includes(q) ||
      r.keywords.some((k) => k.toLowerCase().includes(q)),
  );
}

// ── cell semantics ─────────────────────────────────────────────────────────────

/** O balcão (PDV): o canal que fica de pé quando se pausam os remotos. */
export const COUNTER_SURFACES: ReadonlySet<string> = new Set(["pdv", "pos", "balcao"]);

export function cellState(
  row: CatalogRowProjection,
  cell: SurfaceCellProjection,
): CellState {
  if (!cell.in_listing) return "absent";
  if (!row.is_active) return "archived";
  // Product-level switches gate every surface; listing-level gates this one.
  // "Ocultar no catálogo" vale para TODOS os canais, PDV incluído (decisão do
  // dono, beta 05/11, GES-10): a grade do PDV também exige o produto publicado.
  const published = row.is_published && cell.is_published;
  const sellable = row.is_sellable && cell.is_sellable;
  if (published && sellable) return "available";
  if (!published) return "unpublished";
  return "paused";
}

const CELL_TONES: Record<CellState, string> = {
  available: "border-success/40 bg-success/10 text-success",
  paused: "border-warning/40 bg-warning/10 text-warning",
  unpublished: "border-border bg-muted text-muted-foreground",
  archived: "border-border bg-muted text-muted-foreground",
  absent: "border-dashed border-border bg-transparent text-muted-foreground/60",
};

const CELL_LABELS: Record<CellState, string> = {
  available: "Disponível",
  paused: "Pausado",
  unpublished: "Oculto",
  archived: "Arquivado",
  absent: "Não ofertado",
};

export function cellView(
  row: CatalogRowProjection,
  cell: SurfaceCellProjection,
): CellView {
  const state = cellState(row, cell);
  return { state, label: CELL_LABELS[state], toneClass: CELL_TONES[state] };
}

// ── status do produto (linha) — esmaecer + foto P&B quando está "fora" ─────────
// Um produto está fora quando NÃO está disponível em nenhum canal. `cell.available`
// já cruza produto × listing, então um único predicado cobre os três caminhos:
// oculto no catálogo, pausado no nível-produto (globalzinho), OU pausado célula a célula
// em todos os canais. Fonte única do esmaecimento/foto P&B (sem casos especiais).

export function availableAnywhere(row: CatalogRowProjection): boolean {
  return row.cells.some((c) => c.in_listing && c.available);
}

export interface RowStatus {
  off: boolean; // esmaecer a linha + foto P&B + nome tachado
  label: string; // selo (vazio = ativo)
  tone: "" | "muted" | "amber" | "danger";
  hint: string; // frase inteira do selo (title) — vazia quando o rótulo se explica
}

/** O vínculo do balcão está publicado e vendendo? */
export function sellsAtCounter(row: CatalogRowProjection): boolean {
  return row.cells.some(
    (cell) =>
      COUNTER_SURFACES.has(cell.surface_ref) &&
      cell.in_listing &&
      cell.is_published &&
      cell.is_sellable,
  );
}

/**
 * Vende só no balcão: o PDV vende e os canais remotos onde o produto está
 * ficaram todos pausados. É assim que se vende só no balcão desde a decisão do
 * dono de 05/11 ("Ocultar" tira de TODOS os canais), e é como nasce o item do
 * "Permitir revenda" (beta 05/11, CMP-08).
 */
export function sellsOnlyAtCounter(row: CatalogRowProjection): boolean {
  const remote = row.cells.filter(
    (cell) => !COUNTER_SURFACES.has(cell.surface_ref) && cell.in_listing,
  );
  return (
    sellsAtCounter(row) &&
    remote.length > 0 &&
    remote.every((cell) => !(cell.is_published && cell.is_sellable))
  );
}

// Escala de estados "fora", do mais deliberado ao mais urgente:
// Oculto (cinza) · Pausado (âmbar) · Esgotado (vermelho/danger).
export function rowStatus(row: CatalogRowProjection): RowStatus {
  if (!row.is_active)
    return { off: true, label: "Arquivado", tone: "muted", hint: "" };
  if (!row.is_published)
    return { off: true, label: "Oculto", tone: "muted", hint: "" };
  if (!row.is_sellable)
    return { off: true, label: "Pausado", tone: "amber", hint: "" };
  // Depois das duas chaves DELIBERADAS e antes de Esgotado, de propósito: aqui
  // ninguém escondeu nada — o produto caiu fora do cardápio como efeito colateral
  // de desativar a categoria. Esgotado se resolve sozinho no próximo lote;
  // este não se resolve nunca, porque não há quem perceba. Rótulo curto (a linha
  // é estreita) + a frase inteira no `hint`; "Oculto" NÃO serve, já quer dizer
  // "não publicado".
  if (row.hidden_by_inactive_collection) {
    return {
      off: true,
      label: "Fora do cardápio",
      tone: "danger",
      hint: "Fora do cardápio: a categoria dele está desativada. Reative a categoria ou mova o produto para outra.",
    };
  }
  // Esgotado = fato de ESTOQUE, ortogonal à pausa. Danger pra saltar à vista (cliente
  // não consegue comprar agora) e diferenciar do Pausado — mesmo repondo no lote.
  // Vem antes de "Indisponível" porque o gate de pausa das células não enxerga estoque.
  if (row.sold_out)
    return { off: true, label: "Esgotado", tone: "danger", hint: "" };
  const listed = row.cells.some((c) => c.in_listing);
  if (listed && !availableAnywhere(row)) {
    return { off: true, label: "Indisponível", tone: "amber", hint: "" };
  }
  // Vendendo, mas só no PDV: não esmaece, só conta (CMP-08).
  if (sellsOnlyAtCounter(row)) {
    return {
      off: false,
      label: "Só no balcão",
      tone: "muted",
      hint: "Só no balcão: vende no PDV. Os outros canais estão pausados até você ligar.",
    };
  }
  return { off: false, label: "", tone: "", hint: "" };
}

// ── preço por célula: só mostra quando DIFERE do base ──────────────────────────
// O preço-base já vive na linha do produto. Repetir "R$ 13,00" em toda célula
// (markup 0) é ruído — a matriz vira um mapa de calor. Quando há override, o preço
// aparece com o sentido do delta (↑ acima / ↓ abaixo do base).

export type PriceDelta = "same" | "up" | "down";

export interface CellPriceView {
  delta: PriceDelta;
  differs: boolean; // preço da célula ≠ base do produto
  display: string; // "R$ 15,00"
}

export function cellPrice(
  row: CatalogRowProjection,
  cell: SurfaceCellProjection,
): CellPriceView {
  const price = cell.price_q ?? row.base_price_q;
  const base = row.base_price_q;
  const delta: PriceDelta =
    price > base ? "up" : price < base ? "down" : "same";
  return { delta, differs: delta !== "same", display: cell.price_display };
}

// ── ícone do canal (por ref) — header compacto da coluna ───────────────────────
const SURFACE_ICONS: Record<string, string> = {
  pdv: "lucide:store",
  web: "lucide:globe",
  whatsapp: "lucide:message-circle",
  ifood: "lucide:bike",
  delivery: "lucide:truck",
};

export function surfaceIcon(ref: string): string {
  return SURFACE_ICONS[ref] ?? "lucide:radio-tower";
}

// Ícone da coluna considerando o tipo: feed traz a própria dica (tv/rss); canal
// resolve por ref. Fonte única do ícone de cabeçalho da matriz.
const DISPLAY_ICONS: Record<string, string> = {
  tv: "lucide:tv",
  rss: "lucide:rss",
  monitor: "lucide:monitor",
};

export function surfaceDisplayIcon(surface: SurfaceProjection): string {
  if (!surface.transactional) return DISPLAY_ICONS[surface.icon] ?? "lucide:tv";
  return surfaceIcon(surface.ref);
}

// ── surface metadata ─────────────────────────────────────────────────────────

// Rótulo CURTO (cabe na coluna estreita da matriz) + `title` com a frase inteira,
// que é o que o operador lê ao pousar o mouse.
const SYNC: Record<
  SurfaceSyncStatus,
  { label: string; title: string; toneClass: string } | null
> = {
  ok: { label: "Em dia", title: "Sincronizado", toneClass: "text-success" },
  error: {
    label: "Erro",
    title: "Erro de sincronização",
    toneClass: "text-error",
  },
  never: {
    label: "Nunca",
    title: "Nunca sincronizado",
    toneClass: "text-warning",
  },
  na: null, // não é alvo de projeção → sem badge
};

export function syncBadge(
  status: SurfaceSyncStatus,
): { label: string; title: string; toneClass: string } | null {
  return SYNC[status];
}

// ── sync por célula (produto × plataforma) — Arc H ─────────────────────────────
// O selo de sync mora na célula: reflete o ÚLTIMO push àquela plataforma, ortogonal
// à disponibilidade (uma célula pode estar "disponível" mas com push em erro). Só
// tem sentido em superfície que projeta (canal com adapter); feed de pull não.

export interface CellSyncView {
  status: CellSyncStatus;
  show: boolean; // renderiza o selo? (esconde em superfície que não projeta)
  label: string; // rótulo curto p/ tooltip/leitor de tela
  icon: string; // ícone Lucide canônico; evita glifo solto com geometria irregular
  color: "success" | "warning" | "error" | "neutral";
  actionable: boolean; // oferece "sincronizar agora"? (error/pending/nunca em alvo)
}

const CELL_SYNC: Record<
  Exclude<CellSyncStatus, "">,
  {
    label: string;
    icon: string;
    color: CellSyncView["color"];
  }
> = {
  synced: {
    label: "Sincronizado",
    icon: "i-lucide-circle-check",
    color: "success",
  },
  pending: {
    label: "Sincronizando",
    icon: "i-lucide-refresh-cw",
    color: "warning",
  },
  error: {
    label: "Erro de sync",
    icon: "i-lucide-triangle-alert",
    color: "error",
  },
  retracted: {
    label: "Retirado",
    icon: "i-lucide-circle-minus",
    color: "neutral",
  },
  skipped: {
    label: "Ignorado",
    icon: "i-lucide-circle-slash",
    color: "neutral",
  },
};

export function cellSyncView(
  surface: SurfaceProjection | undefined,
  cell: SurfaceCellProjection,
): CellSyncView {
  // Superfície que não projeta (feed de pull) → sem selo de sync.
  const projects = !!surface?.is_projection_target;
  if (!projects) {
    return {
      status: cell.sync_status,
      show: false,
      label: "",
      icon: "",
      color: "neutral",
      actionable: false,
    };
  }
  const status = cell.sync_status;
  if (status === "") {
    // alvo de projeção que nunca sincronizou → estado "nunca", acionável.
    return {
      status,
      show: cell.in_listing,
      label: "Nunca sincronizado",
      icon: "i-lucide-circle-help",
      color: "neutral",
      actionable: cell.in_listing,
    };
  }
  const meta = CELL_SYNC[status];
  return {
    status,
    show: true,
    label: meta.label,
    icon: meta.icon,
    color: meta.color,
    actionable: status === "error" || status === "pending",
  };
}

// Conta as células em erro de uma linha (badge de atenção na coluna do produto).
export function syncErrorCount(
  row: CatalogRowProjection,
  surfaces: SurfaceProjection[],
): number {
  const targets = new Set(
    surfaces.filter((s) => s.is_projection_target).map((s) => s.ref),
  );
  return row.cells.filter(
    (c) => targets.has(c.surface_ref) && c.sync_status === "error",
  ).length;
}

// ── PIM social (resumo da linha) — Arc H ───────────────────────────────────────
// O painel PIM edita os campos; este resumo é o que a linha mostra de relance: os
// campos essenciais preenchidos e o que falta p/ um feed comercial (Google/Meta).

export interface PimSummary {
  complete: boolean;
  brand: string;
  category: string;
  filled: number; // campos essenciais preenchidos (0..3: brand, categoria, gtin)
  missing: string[]; // rótulos do que falta p/ prontidão de feed
}

export function pimSummary(row: CatalogRowProjection): PimSummary {
  const s = row.social;
  const missing: string[] = [];
  if (!s.brand) missing.push("marca");
  if (!s.google_product_category) missing.push("categoria");
  const filled = [s.brand, s.google_product_category, s.gtin].filter(
    Boolean,
  ).length;
  return {
    complete: row.pim_complete,
    brand: s.brand,
    category: s.google_product_category,
    filled,
    missing,
  };
}

// ── inicial do avatar do produto (G20) ─────────────────────────────────────────
// Sem foto, ou com a foto quebrada, o UAvatar oficial mostra uma inicial. A cor e
// a geometria pertencem ao tema Nuxt UI; o app não mantém uma paleta paralela.
export function letterTile(name: string): { letter: string } {
  const clean = (name || "").trim();
  const letter = (clean.match(/[\p{L}\p{N}]/u)?.[0] ?? "?").toUpperCase();
  return { letter };
}

// ── Exportar (⋯ do cabeçalho, v3) ────────────────────────────────────────────
// O recorte da página atual. As cinco primeiras colunas formam o contrato editável
// da importação; coleção e canais são contexto explícito, não comandos de escrita.
export function catalogCsv(
  rows: CatalogRowProjection[],
  surfaces: SurfaceProjection[],
): string {
  // Escrito pelo kit (`readingCsvText`): ";" entre colunas e BOM, como a planilha em
  // português lê; o preço sai como número em reais ("18,00"), para a planilha somar.
  return readingCsvText({
    header: [
      "SKU",
      "Produto",
      "Preço (R$)",
      "Publicado",
      "À venda",
      "Coleção (informativa)",
      ...surfaces.map((s) => `Canal: ${s.name}`),
    ],
    rows: rows.map((row) => {
      const bySurface = new Map(row.cells.map((cell) => [cell.surface_ref, cell]));
      return [
        row.sku,
        row.name,
        readingCsvMoney(row.base_price_q / 100),
        row.is_published ? "Sim" : "Não",
        row.is_sellable ? "Sim" : "Não",
        row.primary_collection_name ?? "",
        ...surfaces.map((s) => {
          const cell = bySurface.get(s.ref);
          return cell ? cellView(row, cell).label : "";
        }),
      ];
    }),
  });
}

/** Vigência pertence ao canal; não altera a disponibilidade por conta própria. */
export function cellValidity(
  cell: Pick<SurfaceCellProjection, "valid_from" | "valid_until">,
): string {
  const date = (value: string) => value.split("-").reverse().join("/");
  if (cell.valid_from && cell.valid_until)
    return `Vale de ${date(cell.valid_from)} até ${date(cell.valid_until)}`;
  if (cell.valid_from) return `Vale a partir de ${date(cell.valid_from)}`;
  if (cell.valid_until) return `Vale até ${date(cell.valid_until)}`;
  return "";
}


/** Canais com a mesma janela compartilham um selo na linha do produto. */
export function rowValidities(row: CatalogRowProjection, surfaces: SurfaceProjection[]) {
  const groups = new Map<string, { label: string; channels: string[] }>();
  for (const cell of row.cells) {
    const label = cellValidity(cell);
    if (!cell.in_listing || !label) continue;
    const surface = surfaces.find((surface) => surface.ref === cell.surface_ref);
    if (!surface?.transactional) continue;
    const group = groups.get(label) ?? { label, channels: [] };
    group.channels.push(surface.short_name || surface.name);
    groups.set(label, group);
  }
  return Array.from(groups.values(), (group) => ({
    label: group.label,
    channels: group.channels.join(", "),
  }));
}

// ── disponibilidade nos canais (painel do produto, aba Geral) ─────────────────
// A linha de cada canal vem do servidor com a mesma fonte da aba Vínculos e do
// Tabelão (beta 05/11, GES-03): `not_listed` é canal onde o produto não está, e não
// conta nem como "à venda" nem como falta. O selo do bloco só diz "À venda em
// todos" quando TODA linha está à venda.

export type ChannelAvailabilityState =
  | "available"
  | "sold_out"
  | "paused"
  | "not_listed";

export interface AvailabilityRowLike {
  readonly state: ChannelAvailabilityState;
  readonly since: string;
}

export interface AvailabilitySummary {
  color: "success" | "error" | "neutral";
  label: string;
}

export function availabilitySummary(
  rows: readonly AvailabilityRowLike[],
): AvailabilitySummary {
  const listed = rows.filter((row) => row.state !== "not_listed");
  const off = listed.filter((row) => row.state !== "available");
  if (off.length) {
    const word = off.some((row) => row.state === "paused") ? "Pausado" : "Esgotado";
    const since = off.map((row) => row.since).filter(Boolean).sort()[0] ?? "";
    const where = off.length === rows.length ? "" : ` em ${off.length} de ${rows.length}`;
    return { color: "error", label: `${word}${where}${since ? ` desde ${since}` : ""}` };
  }
  if (!listed.length) return { color: "neutral", label: "Fora de todos os canais" };
  if (listed.length < rows.length)
    return { color: "neutral", label: `À venda em ${listed.length} de ${rows.length}` };
  return { color: "success", label: "À venda em todos" };
}

/** O que a linha do canal diz, na voz da tela. */
export function availabilityRowLabel(row: {
  state: ChannelAvailabilityState;
  kind: "sale" | "display";
}): string {
  if (row.state === "available") return "À venda";
  if (row.state === "not_listed") return "Não incluído";
  if (row.state === "paused") return "Pausado";
  return row.kind === "display" ? "Fora de estoque" : "Esgotado";
}

// ── Vendido por peso: o que acontece com os canais remotos ao salvar (GES-02) ──
// Ligar pausa a Loja online, o iFood e o WhatsApp (o preço sai da balança); desligar
// religa o que a regra pausou. A tela avisa ANTES de salvar, com o nome dos canais.

function joinNames(names: string[]): string {
  return names.length <= 1
    ? (names[0] ?? "")
    : `${names.slice(0, -1).join(", ")} e ${names.at(-1)}`;
}

export function weighedChannelsNotice(input: {
  /** A unidade gravada (antes de salvar) e a do rascunho. */
  savedUnit: string;
  draftUnit: string;
  /** Os canais de venda remotos onde o produto está hoje (nome). */
  remoteChannels: readonly string[];
}): string {
  const saved = input.savedUnit.trim().toLowerCase() === "kg";
  const draft = input.draftUnit.trim().toLowerCase() === "kg";
  if (draft && !saved) {
    const names = joinNames([...input.remoteChannels]);
    return names
      ? `Vendido só no balcão: o preço final sai da balança. Ao salvar, sai de ${names}; desmarcar depois traz de volta.`
      : "Vendido só no balcão: o preço final sai da balança.";
  }
  if (draft) return "Vendido só no balcão: o preço final sai da balança.";
  if (saved)
    return "Ao salvar, volta para os canais de onde saiu por ser vendido por peso.";
  return "";
}

// ── o canal na linha do produto, no celular (GES-19) ─────────────────────────
// No celular as colunas de canal somem (`meta.supporting`): a tabela tinha 1008 px
// num cartão de 343 px, e só a coluna do PDV aparecia, sem preço. A linha do
// produto passa a dizer, em pílulas, onde ele está e por quanto.

export interface PhoneChannelChip {
  ref: string;
  label: string;
  tone: "success" | "warning" | "neutral";
}

export function phoneChannelChips(
  row: CatalogRowProjection,
  surfaces: readonly SurfaceProjection[],
): PhoneChannelChip[] {
  return surfaces
    .filter((surface) => surface.transactional)
    .flatMap((surface) => {
      const cell = row.cells.find((item) => item.surface_ref === surface.ref);
      if (!cell?.in_listing) return [];
      const view = cellView(row, cell);
      const price = cell.price_display ? ` ${cell.price_display}` : "";
      const label =
        view.state === "available"
          ? `${surface.short_name}${price}`
          : `${surface.short_name} ${view.label.toLocaleLowerCase("pt-BR")}`;
      const tone =
        view.state === "available"
          ? "success"
          : view.state === "paused"
            ? "warning"
            : "neutral";
      return [{ ref: surface.ref, label, tone } as PhoneChannelChip];
    });
}

// ── preço por canal: maior que zero, dito no campo (GES-05) ──────────────────
// O PDV trata preço zero como "Sem preço" e não vende; o servidor recusa. A tela
// diz o porquê no campo, antes de enviar (negativo deixava o botão inerte, calado).

/** Centavos do texto digitado ("12,50" → 1250); `null` se não é número. */
export function parseChannelPrice(text: string): number | null {
  const cleaned = text
    .replace(/[^0-9,.-]/g, "")
    .replace(/\./g, "")
    .replace(",", ".");
  if (!cleaned) return null;
  const value = Number.parseFloat(cleaned);
  return Number.isFinite(value) ? Math.round(value * 100) : null;
}

/** A recusa do campo, ou vazio quando o preço serve. */
export function channelPriceError(text: string): string {
  const price = parseChannelPrice(text);
  if (price === null) return "Informe o preço em reais, como 12,50.";
  if (price <= 0) return "O preço precisa ser maior que zero.";
  return "";
}
