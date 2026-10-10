// A COLUNA DA COMANDA (WP-PDV-COLUNA-COMANDA, decisões do dono de 10/10/2026).
//
// Quatro zonas fixas: o cabeçalho (o que a comanda É, e a porta "Comanda ⋯"), a lista,
// o bloco de ação (o objeto em foco) e o pé (Enviar · Dividir conta · Pagamento). O que
// muda é o OBJETO em foco: a comanda, uma linha aberta ou várias linhas marcadas.
//
// MARCAR NÃO É MODO: a linha aberta é a primeira marcada; marcar outra transforma o
// bloco de 1 no bloco de N, nas mesmas posições. Desmarcar até sobrar uma volta ao
// editor daquela. Este módulo é a regra pura disso; a tela só desenha.
import type { POSCartItem } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";
import { lineTotalQ } from "~/presentation/lineDiscounts";
import { countUnits } from "~/presentation/selection";
import { isWeighedLine } from "~/presentation/weighed";

export interface MarkResult {
  /** As linhas marcadas depois do gesto (vazio quando o foco é uma linha só). */
  marked: Set<string>;
  /** A linha que o editor abre quando sobra uma só (ou "" para não mexer). */
  open: string;
}

/**
 * Marcar ou desmarcar uma linha. `openLineId` é a linha aberta no editor (ou ""): ela
 * entra na conta como a primeira marcada. Conjunto de um não existe: vira a linha
 * aberta (o bloco de 1).
 */
export function toggleMark(marked: ReadonlySet<string>, lineId: string, openLineId: string): MarkResult {
  const next = new Set(marked);
  if (!next.size && openLineId) next.add(openLineId);
  if (next.has(lineId)) next.delete(lineId);
  else next.add(lineId);
  return normalizeMarks(next);
}

/** Shift + clique: marca o intervalo entre a última marcada (ou a aberta) e esta. */
export function markRange(
  items: readonly POSCartItem[],
  marked: ReadonlySet<string>,
  anchorId: string,
  lineId: string,
): MarkResult {
  const ids = items.map((item) => item.line_id);
  const from = ids.indexOf(anchorId);
  const to = ids.indexOf(lineId);
  if (from < 0 || to < 0) return toggleMark(marked, lineId, "");
  const next = new Set(marked);
  const [start, end] = from < to ? [from, to] : [to, from];
  for (let index = start; index <= end; index += 1) next.add(ids[index]!);
  return normalizeMarks(next);
}

function normalizeMarks(next: Set<string>): MarkResult {
  if (next.size === 1) return { marked: new Set(), open: [...next][0]! };
  return { marked: next, open: "" };
}

export interface MarkedSummary {
  lines: number;
  units: number;
  totalQ: number;
  /** "3 linhas marcadas · 5 itens · R$ 61,70": o objeto do bloco, no título. */
  title: string;
  /** Alguma marcada é peça pesada: no lote, o desconto é só em % (R$ viraria por quilo). */
  hasWeighed: boolean;
}

export function markedSummary(items: readonly POSCartItem[], marked: ReadonlySet<string>): MarkedSummary {
  const chosen = items.filter((item) => marked.has(item.line_id));
  const units = countUnits(chosen);
  const totalQ = chosen.reduce((sum, item) => sum + lineTotalQ(item), 0);
  const lines = chosen.length;
  return {
    lines,
    units,
    totalQ,
    title: `${lines} ${lines === 1 ? "linha marcada" : "linhas marcadas"} · ${units} ${units === 1 ? "item" : "itens"} · ${formatBRL(totalQ)}`,
    hasWeighed: chosen.some((item) => isWeighedLine(item)),
  };
}

export interface FireCellInput {
  /** Itens a enviar na comanda inteira (o `fireBarView`). */
  unfired: number;
  /** O rótulo do servidor para enviar ("Enviar à cozinha") ou o estado ("Enviado"). */
  label: string;
  disabled: boolean;
  /** Linhas marcadas (2 ou mais) e, delas, as que ainda não foram à cozinha. */
  markedLines: number;
  markedFirable: number;
  offline: boolean;
}

export interface FireCellView {
  label: string;
  shortLabel?: string;
  /** O número no chip ao lado do rótulo (só quando o rótulo não o diz). */
  count: number;
  disabled: boolean;
  title: string;
  /** Envia só as marcadas (F9 também). */
  onlyMarked: boolean;
}

/**
 * O primeiro botão do pé SEGUE O FOCO (decisão 4 do dono): com linhas marcadas, envia
 * só elas e diz isso ("Enviar 3 marcadas"). Sem conexão, apagado com o motivo.
 */
export function fireCellView(input: FireCellInput): FireCellView {
  if (input.markedLines >= 2) {
    const n = input.markedFirable;
    if (!n) {
      return {
        label: "Marcadas já enviadas",
        shortLabel: "Enviadas",
        count: 0,
        disabled: true,
        title: "As linhas marcadas já estão na cozinha",
        onlyMarked: true,
      };
    }
    return {
      label: `Enviar ${n} ${n === 1 ? "marcada" : "marcadas"}`,
      shortLabel: `Enviar ${n}`,
      count: 0,
      disabled: input.disabled || input.offline,
      title: input.offline
        ? "Cozinha sem conexão: avise de voz"
        : `Enviar à cozinha só ${n === 1 ? "a linha marcada" : `as ${n} linhas marcadas`} (F9)`,
      onlyMarked: true,
    };
  }
  return {
    label: input.label,
    shortLabel: input.unfired ? "Enviar" : undefined,
    count: input.unfired,
    disabled: input.disabled || (input.offline && input.unfired > 0),
    title: input.offline && input.unfired
      ? "Cozinha sem conexão: avise de voz"
      : input.unfired
        ? `${input.label} as linhas novas (F9)`
        : "Tudo o que é da cozinha já foi enviado",
    onlyMarked: false,
  };
}

export interface KitchenStateView {
  /** "10 a enviar · 1 na cozinha" */
  counts: string;
  /** O envio automático, com o QUANDO; ou o motivo de a cozinha não receber agora. */
  /** `wide`: a frase inteira só cabe na coluna larga (30 rem); abaixo, a curta. */
  auto: { full: string; short: string; tone: "muted" | "warning"; wide: boolean };
  /** O toque leva aos Ajustes (só o envio automático; sem conexão não leva a nada). */
  linksToSettings: boolean;
}

/**
 * O estado da cozinha em palavra: o que falta, o que já foi e QUANDO o envio automático
 * manda sozinho. O relógio de `pages/index.vue` envia ao sair da comanda ou depois de
 * 90 s sem mudança; a frase diz isso, e não só "ligado".
 */
export function kitchenStateView(args: { unfired: number; fired: number; autoFire: boolean; offline: boolean }): KitchenStateView {
  const parts: string[] = [];
  if (args.unfired) parts.push(`${args.unfired} a enviar`);
  if (args.fired) parts.push(`${args.fired} na cozinha`);
  if (args.offline) {
    return {
      counts: parts.join(" · "),
      auto: { full: "cozinha sem conexão: avise de voz", short: "cozinha sem conexão", tone: "warning", wide: false },
      linksToSettings: false,
    };
  }
  return {
    counts: parts.join(" · "),
    auto: args.autoFire
      ? { full: "envio automático: ao sair ou após 90 s parada", short: "automático: ao sair", tone: "muted", wide: true }
      : { full: "envio automático: desligado", short: "automático desligado", tone: "muted", wide: false },
    linksToSettings: true,
  };
}
