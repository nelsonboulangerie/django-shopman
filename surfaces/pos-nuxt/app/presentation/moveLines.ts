// Presentation: TRANSFERIR itens entre comandas (spec §2.3, preço congelado no movimento).
//
// TRANSFERIR É A AÇÃO ÚNICA, SEM MODOS (dono, N=1, 13/10/2026). O diálogo "Transferir"
// tem um campo só, "Para qual comanda?", que recebe o leitor (bipar), a digitação e a
// escolha numa lista das comandas em uso. Ao abrir, a ação padrão já está escolhida: uma
// comanda NOVA pré-nomeada ("13-2", editável ali mesmo). Enter confirma. Bipou ou
// escolheu uma comanda em uso, o destino passa a ser ela. O botão diz o resultado em
// palavras ("Levar 3 itens para a #12"). Vão os itens marcados, ou todos quando nada
// está marcado; a comanda que fica vazia é liberada sozinha, com Desfazer (T2=1).
//
// Funções puras: a tela desenha o que sai daqui e entrega o comando a `submitMove`, que
// chama a Action `move_tab_lines`. O Core congela o preço de cada linha como foi cobrado
// na origem; este módulo só deixa a tela dizer isso, nunca reprecifica.

import type { POSCartItem, POSSeatingSpotOption, POSTabProjection } from "~/types/pos";
import { countUnits } from "~/presentation/selection";
import { isWeighedLine, lineQtyLabel } from "~/presentation/weighed";

interface TabManipulationCapability {
  allows_split?: boolean;
  allows_transfer?: boolean;
  allows_merge?: boolean;
  freezes_price_on_move?: boolean;
}

function asCapability(capability: unknown): TabManipulationCapability | null {
  return capability && typeof capability === "object" ? (capability as TabManipulationCapability) : null;
}

/** O canal deixa a transferência abrir uma comanda nova (`allows_split`). Sem a
 *  capacidade declarada (defensivo), deixa. */
export function allowsNewTab(capability: unknown): boolean {
  const cap = asCapability(capability);
  return cap ? Boolean(cap.allows_split) : true;
}

/** O canal deixa levar itens para uma comanda em uso (`allows_transfer`). */
export function allowsExistingTab(capability: unknown): boolean {
  const cap = asCapability(capability);
  return cap ? Boolean(cap.allows_transfer || cap.allows_merge) : true;
}

/**
 * O movimento congela o preço de cada linha (invariante do `move_lines`). Pela
 * capacidade; o padrão é `true`, porque o Core sempre congela o preço cobrado.
 */
export function freezesPriceOnMove(capability: unknown): boolean {
  const cap = asCapability(capability);
  return cap ? cap.freezes_price_on_move !== false : true;
}

/**
 * Identidade que endereça uma linha no movimento: o `line_id`, e só ele (o SKU
 * endereçaria a linha errada na comanda com dois chás).
 */
export function moveLineId(item: POSCartItem): string {
  return item.line_id;
}

/** O título da comanda como o balcão fala: "#13" no número, o nome como está ("Mesa 6"). */
export function tabLabel(display: string): string {
  const value = String(display || "").trim().replace(/^#/, "");
  return /^\d+$/.test(value) ? `#${value}` : value;
}

/** O que vai: as marcadas, na ordem da comanda; nada marcado, a comanda inteira. */
export function linesToMove(items: readonly POSCartItem[], preselected: readonly string[] | undefined): POSCartItem[] {
  const chosen = new Set(preselected || []);
  const marked = items.filter((item) => chosen.has(moveLineId(item)));
  return marked.length ? marked : [...items];
}

/** As linhas escolhidas são TODAS as da comanda: a origem vai ficar vazia. */
export function movesEverything(items: readonly POSCartItem[], selectedIds: readonly string[]): boolean {
  if (!items.length) return false;
  const chosen = new Set(selectedIds);
  return items.every((item) => chosen.has(moveLineId(item)));
}

/** A frase do toast quando a origem vazia foi liberada sozinha. */
export function sourceReleasedMessage(tabTitle: string): string {
  return tabTitle ? `Comanda ${tabTitle} ficou vazia e foi liberada.` : "A comanda ficou vazia e foi liberada.";
}

// ── O destino ───────────────────────────────────────────────────────────────────────

export interface MoveTargetOption {
  sessionKey: string;
  /** "#12", "Mesa 6" ou "Mesa 4 (#12)": o que o operador lê e o que o CTA diz. */
  title: string;
  /** "#12 · Ana Souza": o botão da lista. */
  label: string;
  /** O que casa com a digitação: número sem zeros, nomes em minúsculas (o da comanda e
   *  o da mesa dela, inteiro e curto). */
  keys: string[];
}

/** Uma mesa LIVRE do Salão (dono, M=1, 13/10/2026): escolhida, a comanda nova nasce nela. */
export interface MoveSpotOption {
  spotRef: string;
  /** "Mesa 4". */
  title: string;
  keys: string[];
}

function matchKey(value: string): string {
  const raw = String(value || "").trim().replace(/^#/, "").toLowerCase();
  return /^\d+$/.test(raw) ? raw.replace(/^0+(?=\d)/, "") : raw;
}

function spotKeys(spot: POSSeatingSpotOption | undefined): string[] {
  return spot ? [matchKey(spot.label), matchKey(spot.short_label)].filter(Boolean) : [];
}

/** As comandas EM USO (com sessão aberta), menos a de origem. A que está numa mesa diz
 *  a mesa primeiro ("Mesa 4 (#12)") e casa também com o nome da mesa. */
export function moveTargetOptions(
  tabs: readonly POSTabProjection[],
  sourceSessionKey = "",
  spots: readonly POSSeatingSpotOption[] = [],
): MoveTargetOption[] {
  const byRef = new Map(spots.map((spot) => [spot.ref, spot]));
  return tabs
    .filter((tab) => tab.session_key && tab.session_key !== sourceSessionKey)
    .map((tab) => {
      const tabTitle = tabLabel(tab.display_ref || tab.ref);
      const spot = tab.seating_spot_ref ? byRef.get(tab.seating_spot_ref) : undefined;
      const title = spot && matchKey(spot.label) !== matchKey(tab.display_ref) ? `${spot.label} (${tabTitle})` : tabTitle;
      return {
        sessionKey: tab.session_key,
        title,
        label: tab.customer_name ? `${title} · ${tab.customer_name}` : title,
        keys: [matchKey(tab.display_ref), matchKey(tab.ref), ...spotKeys(spot)].filter(Boolean),
      };
    });
}

/** As mesas LIVRES do Salão de hoje: nenhuma comanda aberta nelas (nem a de origem). */
export function freeSpotOptions(
  spots: readonly POSSeatingSpotOption[],
  tabs: readonly POSTabProjection[],
  sourceSpotRef = "",
): MoveSpotOption[] {
  const taken = new Set([sourceSpotRef, ...tabs.filter((tab) => tab.session_key).map((tab) => tab.seating_spot_ref || "")].filter(Boolean));
  return spots
    .filter((spot) => !taken.has(spot.ref))
    .map((spot) => ({ spotRef: spot.ref, title: spot.label, keys: spotKeys(spot) }));
}

/** As opções da lista que casam com o que está no campo (começo do número ou do nome,
 *  ou do cliente). Com o campo vazio, no nome sugerido, ou sem nenhuma que case (um nome
 *  novo), todas: a lista nunca some de quem quer escolher. */
export function filterTargets<T extends { keys: string[]; title: string; label?: string }>(options: readonly T[], query: string, suggested: string): T[] {
  const q = matchKey(query);
  if (!q || q === matchKey(suggested)) return [...options];
  const hits = options.filter((option) => option.keys.some((key) => key.startsWith(q)) || (option.label || option.title).toLowerCase().includes(q));
  return hits.length ? hits : [...options];
}

export type MoveDestination =
  | { kind: "existing"; sessionKey: string; title: string }
  | { kind: "new"; tabRef: string; title: string; spotRef?: string; spotTitle?: string }
  | { kind: "invalid"; reason: string };

/**
 * O que o campo quer dizer AGORA: uma comanda em uso (casou o número, o nome ou a mesa
 * dela), uma mesa livre (a comanda nova nasce nela, com o nome sugerido), uma comanda
 * nova com esse nome, ou nada que se possa usar (com o motivo em palavras). A barra o
 * servidor recusa; aqui a recusa vem antes, com o formato que funciona.
 */
export function resolveDestination(args: {
  input: string;
  options: readonly MoveTargetOption[];
  spots?: readonly MoveSpotOption[];
  sourceDisplay: string;
  /** As chaves da mesa da comanda de origem (o nome dela não é destino). */
  sourceSpotKeys?: readonly string[];
  suggested: string;
  allowsNew: boolean;
  allowsExisting: boolean;
}): MoveDestination {
  const raw = String(args.input || "").trim().replace(/^#/, "");
  if (!raw) return { kind: "invalid", reason: "Diga para qual comanda os itens vão." };
  const key = matchKey(raw);
  if (key === matchKey(args.sourceDisplay) || (args.sourceSpotKeys || []).map(matchKey).includes(key)) {
    return { kind: "invalid", reason: "É a própria comanda. Escolha outra ou dê um nome novo." };
  }
  const existing = args.options.find((option) => option.keys.includes(key));
  if (existing) {
    if (!args.allowsExisting) return { kind: "invalid", reason: "Este canal não leva itens para uma comanda em uso." };
    return { kind: "existing", sessionKey: existing.sessionKey, title: existing.title };
  }
  const spot = (args.spots || []).find((option) => option.keys.includes(key));
  if (spot) {
    if (!args.allowsNew) return { kind: "invalid", reason: "Este canal não abre comanda nova pela transferência." };
    const name = args.suggested || "";
    if (!name) return { kind: "invalid", reason: "Dê um nome para a comanda nova." };
    return { kind: "new", tabRef: name, title: tabLabel(name), spotRef: spot.spotRef, spotTitle: spot.title };
  }
  if (/[/\\?#%]/.test(raw)) {
    return { kind: "invalid", reason: `A comanda não pode ter barra. Use um hífen, por exemplo ${args.suggested || "13-2"}.` };
  }
  if (!args.allowsNew) return { kind: "invalid", reason: "Este canal não abre comanda nova pela transferência." };
  return { kind: "new", tabRef: raw, title: tabLabel(raw) };
}

/**
 * O botão diz o RESULTADO em palavras (dono, N=1): para onde, quanto, e o que acontece
 * com a origem quando vai tudo.
 */
export function transferCta(args: { units: number; all: boolean; destination: MoveDestination; sourceTitle: string }): string {
  const { destination } = args;
  if (destination.kind === "invalid") return "Transferir";
  const amount = args.units === 1 ? "1 item" : `${args.units} itens`;
  if (destination.kind === "existing") {
    return args.all
      ? `Levar tudo para a ${destination.title} e liberar a ${args.sourceTitle}`
      : `Levar ${amount} para a ${destination.title}`;
  }
  const where = destination.spotTitle ? `comanda nova ${destination.title} (${destination.spotTitle})` : `comanda nova ${destination.title}`;
  return args.all
    ? `Levar tudo para a ${where} e liberar a ${args.sourceTitle}`
    : `Separar ${amount} na ${where}`;
}

export interface MovePayload {
  mode: "split" | "transfer";
  lineIds: string[];
  toTabRef?: string;
  toSessionKey?: string;
  /** A mesa livre onde a comanda nova nasce (dono, M=1). */
  seatingSpotRef?: string;
  closeSource?: boolean;
}

/**
 * O comando `move_tab_lines` para o destino resolvido, ou `null` quando ainda não há
 * o que mandar. Levar todos os itens pede ao servidor que libere a origem (ele só
 * libera se ela ficou vazia de fato; T2=1).
 */
export function buildMovePayload(args: {
  items: readonly POSCartItem[];
  lineIds: string[];
  destination: MoveDestination;
}): MovePayload | null {
  if (!args.lineIds.length || args.destination.kind === "invalid") return null;
  const closeSource = movesEverything(args.items, args.lineIds) ? { closeSource: true } : {};
  if (args.destination.kind === "existing") {
    return { mode: "transfer", lineIds: args.lineIds, toSessionKey: args.destination.sessionKey, ...closeSource };
  }
  const seated = args.destination.spotRef ? { seatingSpotRef: args.destination.spotRef } : {};
  return { mode: "split", lineIds: args.lineIds, toTabRef: args.destination.tabRef, ...seated, ...closeSource };
}

/** "3 itens: 2× Croissant, 1× Pain au chocolat" (o que vai, numa frase). */
export function movingSummary(lines: readonly POSCartItem[]): { units: number; text: string } {
  const units = countUnits(lines);
  const names = lines.map((item) => (isWeighedLine(item) ? `${lineQtyLabel(item)} ${item.name}` : `${item.qty}× ${item.name}`)).join(", ");
  return { units, text: `${units === 1 ? "1 item" : `${units} itens`}: ${names}` };
}
