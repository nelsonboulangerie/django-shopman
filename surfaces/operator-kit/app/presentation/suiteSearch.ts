// Busca da suíte (SUITE-UX-V2 §2.2, FUNCTION §7; prévias v3 `depois-gestor-busca`,
// `depois-hub-celular` e v4 `hub.jpg`): um campo, uma tecla (`/` ou Ctrl K), três alcances.
//
//   - Esta tela: o filtro que a própria tela já fazia (o quadro do Gestor, a matriz da
//     Produção…), aplicado enquanto se digita. Só existe onde a tela filtra.
//   - App: o resultado da suíte recortado pelo app atual.
//   - Toda a suíte: pedidos, encomendas, clientes, produtos, insumos, fornecedores, lotes,
//     receitas, campanhas e telas de TODOS os apps que o operador abre
//     (`GET /api/v1/backstage/search/`, já recortado por permissão no Django).
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
  suiteScope: "Toda a suíte",
  screenScope: "Esta tela",
  screenSection: "Nesta tela",
  suiteSection: "Na suíte",
  tabHint: "Tab troca o alcance",
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

/** Os alcances desta tela, na ordem do controle (Tab anda por eles). */
export function suiteScopes(options: { hasScreen: boolean; appRef: string }): SuiteSearchScope[] {
  const scopes: SuiteSearchScope[] = [];
  if (options.hasScreen) scopes.push("screen");
  if (options.appRef) scopes.push("app");
  scopes.push("suite");
  return scopes;
}

/** Tab avança, Shift+Tab volta; o último dá a volta. */
export function nextSuiteScope(scopes: SuiteSearchScope[], current: SuiteSearchScope, back = false): SuiteSearchScope {
  const index = Math.max(0, scopes.indexOf(current));
  const step = back ? -1 : 1;
  return scopes[(index + step + scopes.length) % scopes.length]!;
}

/**
 * Os grupos que o alcance mostra. "Esta tela" mostra a suíte inteira logo abaixo do filtro
 * (a prévia v3: "Resultados desta tela primeiro; logo abaixo, a suíte").
 */
export function groupsForScope(groups: SuiteSearchGroup[], scope: SuiteSearchScope, appRef: string): SuiteSearchGroup[] {
  if (scope !== "app") return groups;
  return groups
    .map((group) => ({ ...group, results: group.results.filter((result) => result.app === appRef) }))
    .filter((group) => group.results.length > 0);
}

/** Recorte por tipo (os chips do celular: "Pedidos 2", "Clientes 2"). Vazio = todos. */
export function groupsForType(groups: SuiteSearchGroup[], type: string): SuiteSearchGroup[] {
  return type ? groups.filter((group) => group.type === type) : groups;
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
