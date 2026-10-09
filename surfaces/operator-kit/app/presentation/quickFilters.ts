// Os filtros rápidos da suíte (`OperatorQuickFilters`, WP-FASE2-UX-OPERADOR K4), a
// parte PURA.
//
// Filtro rápido é navegação secundária: mora na barra superior secundária (a toolbar do
// `OperatorPageHeader`, `#filters-primary`), à esquerda, e é UM toque com a contagem ao
// lado (decisão do dono, P1 de 02/10: o recorte de todo dia não se esconde dentro do
// painel de filtros). O painel (`OperatorFilterPanel`) continua sendo o lugar dos
// filtros completos; o recorte rápido ligado aparece também como chip removível.
//
// Três jeitos de ser, pela forma dos itens e da prop `multiple`:
//
//   route     todo item tem `to`: é SUB-SEÇÃO, muda a URL. Ativo é o item cuja rota é
//             a de agora.
//   single    `v-model` com uma chave: um recorte de cada vez (a tela oferece "Todos").
//   multiple  `v-model` com várias chaves: recortes que somam, cada um liga e desliga.
//
// Os favoritos fixados (os `SavedView` com `pinned`) entram no FIM da faixa: aplicar
// um favorito é aplicar o recorte inteiro dele.
//
// No celular, até `QUICK_FILTERS_PHONE_MAX` opções rolam na faixa (sem cortar rótulo);
// mais que isso viram um `NuxtSelect`. Nenhuma decisão de árvore em JS: as duas formas
// existem e a régua é CSS (`max-sm:hidden` / `sm:hidden`).

/** Um item da faixa. `count` sai no chip de contagem da suíte (zero não aparece). */
export interface QuickFilterItem {
  key: string;
  label: string;
  count?: number | null;
  icon?: string;
  /** Sub-seção: a rota para onde o item leva (muda a URL). */
  to?: string;
  disabled?: boolean;
}

export type QuickFiltersMode = "route" | "single" | "multiple";

/** Até quantas opções a faixa rola no celular; acima disso vira `NuxtSelect`. */
export const QUICK_FILTERS_PHONE_MAX = 4;

export function quickFiltersMode(items: readonly QuickFilterItem[], multiple = false): QuickFiltersMode {
  if (items.length > 0 && items.every((item) => Boolean(item.to))) return "route";
  return multiple ? "multiple" : "single";
}

/** As chaves ligadas, como lista, qualquer que seja a forma do modelo. */
export function quickKeys(model: string | readonly string[] | null | undefined): string[] {
  if (Array.isArray(model)) return model.filter(Boolean);
  return typeof model === "string" && model ? [model] : [];
}

export function isQuickActive(model: string | readonly string[] | null | undefined, key: string): boolean {
  return quickKeys(model).includes(key);
}

/**
 * O modelo depois do toque num item. Vários: liga ou desliga a chave, na ordem dos
 * itens (a URL sai sempre igual para o mesmo recorte). Um: a chave tocada.
 */
export function toggleQuick(
  model: string | readonly string[] | null | undefined,
  key: string,
  items: readonly QuickFilterItem[],
  multiple: boolean,
): string | string[] {
  if (!multiple) return key;
  const on = new Set(quickKeys(model));
  if (on.has(key)) on.delete(key);
  else on.add(key);
  return items.map((item) => item.key).filter((itemKey) => on.has(itemKey));
}

function pathOf(to: string): { path: string; query: URLSearchParams } {
  const [path = "", search = ""] = to.split("?");
  return { path: path.replace(/\/+$/, "") || "/", query: new URLSearchParams(search) };
}

/**
 * A sub-seção ativa: o item cuja rota é a de agora. O caminho tem de bater, e cada
 * parâmetro que o `to` declara também; o caminho mais longo vence (`/base/items`
 * antes de `/base`).
 */
export function routeActiveKey(
  items: readonly QuickFilterItem[],
  current: { path: string; query?: Record<string, unknown> },
): string {
  const here = pathOf(current.path).path;
  let best = "";
  let bestLength = -1;
  for (const item of items) {
    if (!item.to) continue;
    const target = pathOf(item.to);
    const prefix = here === target.path || here.startsWith(`${target.path === "/" ? "" : target.path}/`);
    if (!prefix) continue;
    let matches = true;
    for (const [name, value] of target.query) {
      const raw = current.query?.[name];
      const actual = Array.isArray(raw) ? raw[0] : raw;
      if (String(actual ?? "") !== value) matches = false;
    }
    if (!matches) continue;
    const length = target.path.length + target.query.toString().length;
    if (length > bestLength) {
      best = item.key;
      bestLength = length;
    }
  }
  return best;
}

/**
 * O próximo item com o foco pelas setas: anda `delta`, dá a volta nas pontas e pula o
 * desligado. `Home`/`End` são `-Infinity`/`Infinity`.
 */
export function nextQuickIndex(items: readonly QuickFilterItem[], current: number, delta: number): number {
  const total = items.length;
  if (!total) return -1;
  if (delta === -Infinity || delta === Infinity) {
    const order = delta === -Infinity ? items.map((_, i) => i) : items.map((_, i) => total - 1 - i);
    return order.find((i) => !items[i]?.disabled) ?? current;
  }
  let index = current;
  for (let step = 0; step < total; step += 1) {
    index = (index + delta + total) % total;
    if (!items[index]?.disabled) return index;
  }
  return current;
}

/** Acima do teto do celular a faixa vira `NuxtSelect` ali. */
export function collapsesOnPhone(items: readonly QuickFilterItem[], max = QUICK_FILTERS_PHONE_MAX): boolean {
  return items.length > max;
}
