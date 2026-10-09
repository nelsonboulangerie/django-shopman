// Busca da suíte (SUITE-UX-V2 §2.2, FUNCTION §7; fase 2, K6: "busca em níveis no
// canônico", dono 09/10/2026): um botão, uma tecla (`/` ou Ctrl K), três níveis, que são
// os GRUPOS do `NuxtDashboardSearch` em ordem fixa:
//
//   - Nesta tela: "Filtrar o quadro por “maria”" vira o recorte da tela. Só existe onde a
//     tela filtra a própria lista.
//   - No app: o que a suíte achou no app atual.
//   - Na suíte: o que achou nos outros apps (pedidos, encomendas, clientes, produtos,
//     insumos, fornecedores, lotes, receitas, campanhas e telas que o operador abre;
//     `GET /api/v1/backstage/search/`, já recortado por permissão no Django).
//
// Aqui fica só o que é puro (tipos, recorte por alcance, contagens, realce, cópia), para
// ser testado sem montar componente; a peça é `OperatorSuiteSearch.vue`.
import { OPERATOR_APPS, type OperatorAppRef } from "../../appIdentity";

export interface SuiteSearchResult {
  key: string;
  type: string;
  /** App de destino, como o Django o chama (`gestor`, `pos`, `kds`…). */
  app: string;
  app_label: string;
  place: string;
  title: string;
  detail: string;
  url: string;
  icon: string;
}

export interface SuiteSearchGroup {
  type: string;
  label: string;
  results: SuiteSearchResult[];
}

export interface SuiteSearchAppCount {
  ref: string;
  label: string;
  count: number;
}

export interface SuiteSearchResponse {
  search: {
    query: string;
    searched: boolean;
    total: number;
    groups: SuiteSearchGroup[];
    apps: SuiteSearchAppCount[];
  };
}

export type SuiteSearchScope = "screen" | "app" | "suite";

/** Menos que isto não vai ao servidor (o mesmo `MIN_QUERY_LENGTH` do Django). */
export const SUITE_SEARCH_MIN_LENGTH = 2;
/** Espera entre a última tecla e a leitura: digitar "maria" faz uma leitura, não cinco. */
export const SUITE_SEARCH_DEBOUNCE_MS = 220;

export const SUITE_SEARCH_COPY = {
  screenSection: "Nesta tela",
  appSection: "No app",
  suiteSection: "Na suíte",
  typeMore: "Digite pelo menos 2 letras para buscar na suíte.",
  searching: "Buscando na suíte…",
  failed: "A busca da suíte não respondeu. O filtro desta tela continua valendo.",
  failedNoScreen: "A busca da suíte não respondeu.",
  retry: "Tentar de novo",
  close: "Fechar a busca",
  clear: "Limpar busca",
  camera: "Ler um código com a câmera",
  cameraHint: "QR do pedido · EAN do insumo · chave da NF",
  cameraUnavailable: "A câmera não abriu. Confira a permissão do navegador para este app.",
  cameraClose: "Fechar a câmera",
  cameraAim: "Aponte para o código. A leitura entra no campo sozinha.",
} as const;

/** O app do kit (chave de `app-identity.json`) pelo nome que o Django usa. */
const KIT_APP_BY_SURFACE: Record<string, OperatorAppRef> = { gestor: "orders" };
const SURFACE_BY_KIT_APP: Record<string, string> = { orders: "gestor" };

/** `operatorPwa.app` (kit) → o `app` dos resultados (Django). A Central não é destino. */
export function surfaceRefForKitApp(kitApp: string | undefined | null): string {
  if (!kitApp || kitApp === "hub") return "";
  return SURFACE_BY_KIT_APP[kitApp] ?? kitApp;
}

/** A cor do app de destino (o selo do resultado), a mesma do ícone do PWA dele. */
export function suiteResultColor(app: string): string {
  const kitApp = (KIT_APP_BY_SURFACE[app] ?? app) as OperatorAppRef;
  return OPERATOR_APPS[kitApp]?.color ?? "";
}

export function normalizeSuiteQuery(raw: string): string {
  return raw.split(/\s+/).filter(Boolean).join(" ");
}

export function suiteQueryReady(raw: string): boolean {
  return normalizeSuiteQuery(raw).length >= SUITE_SEARCH_MIN_LENGTH;
}

/** Um resultado com o nome do tipo dele ("Pedidos"), para o nível que o mostra. */
export interface SuiteLevelResult {
  result: SuiteSearchResult;
  typeLabel: string;
}

/**
 * Os resultados da suíte nos dois níveis de baixo: "No app" (o app atual) e "Na suíte"
 * (os outros). Cada resultado mora em um nível só, na ordem dos grupos do servidor.
 * Sem app (a Central), tudo é "Na suíte".
 */
export function suiteLevels(
  groups: SuiteSearchGroup[],
  appRef: string,
): { app: SuiteLevelResult[]; suite: SuiteLevelResult[] } {
  const app: SuiteLevelResult[] = [];
  const suite: SuiteLevelResult[] = [];
  for (const group of groups) {
    for (const result of group.results) {
      (appRef && result.app === appRef ? app : suite).push({ result, typeLabel: group.label });
    }
  }
  return { app, suite };
}

/**
 * O alvo da frase "Filtrar … por “x”", a partir do `screen-label` da tela ("filtrando
 * o quadro" → "o quadro"). Sem rótulo, "esta tela".
 */
export function suiteScreenTarget(screenLabel: string): string {
  const target = screenLabel.trim().replace(/^filtrando\s+/i, "").trim();
  return target || "esta tela";
}

export function flattenGroups(groups: SuiteSearchGroup[]): SuiteSearchResult[] {
  return groups.flatMap((group) => group.results);
}

export function suiteTotal(groups: SuiteSearchGroup[]): number {
  return groups.reduce((total, group) => total + group.results.length, 0);
}

export function appCount(apps: SuiteSearchAppCount[], appRef: string): number {
  return apps.find((app) => app.ref === appRef)?.count ?? 0;
}

export interface HighlightPart {
  text: string;
  match: boolean;
}

function fold(value: string): string {
  return value.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** Parte o texto em trechos para marcar o termo (sem acento, sem caixa: "maria" acha "María"). */
export function highlightParts(text: string, rawQuery: string): HighlightPart[] {
  const query = normalizeSuiteQuery(rawQuery);
  if (!text) return [];
  if (!query) return [{ text, match: false }];
  const haystack = fold(text);
  const needle = fold(query);
  // A dobra preserva o comprimento só para letras latinas compostas; se mudar, não marca.
  if (haystack.length !== text.length) return [{ text, match: false }];
  const parts: HighlightPart[] = [];
  let cursor = 0;
  let index = haystack.indexOf(needle, cursor);
  while (index >= 0 && needle) {
    if (index > cursor) parts.push({ text: text.slice(cursor, index), match: false });
    parts.push({ text: text.slice(index, index + needle.length), match: true });
    cursor = index + needle.length;
    index = haystack.indexOf(needle, cursor);
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), match: false });
  return parts;
}

/** "Nada na suíte com “maria”." / "Nada no Gestor com “maria”." */
export function suiteEmptyCopy(query: string, scope: SuiteSearchScope, appLabel: string): string {
  const where = scope === "app" && appLabel ? `em ${appLabel}` : "na suíte";
  return `Nada ${where} com “${normalizeSuiteQuery(query)}”.`;
}

/** Nome acessível do resultado: o que é, onde abre e o detalhe, numa frase. */
export function suiteResultLabel(result: SuiteSearchResult): string {
  return [result.title, result.place, result.detail].filter(Boolean).join(", ");
}

/** O alvo do evento é campo de digitação? (a tecla "/" não rouba o que se está escrevendo) */
export function isTypingTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  if (!element || typeof element !== "object") return false;
  const tag = element.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || Boolean(element.isContentEditable);
}

/**
 * A tecla abre a busca? `/` fora de campo; Ctrl K (ou ⌘K) em qualquer lugar. Onde a tela
 * já usa `/` para o próprio campo (a Venda e as Encomendas do PDV), `slash: false`: só
 * Ctrl K abre a suíte.
 */
export function suiteSearchHotkey(
  event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "target">,
  options: { slash?: boolean } = {},
): boolean {
  if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") return true;
  if (options.slash === false) return false;
  return event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !isTypingTarget(event.target);
}
