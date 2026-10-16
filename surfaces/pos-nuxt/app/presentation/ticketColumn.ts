// A COLUNA DA COMANDA (WP-PDV-COLUNA-COMANDA, decisões do dono de 10/10/2026).
//
// Quatro zonas fixas: o cabeçalho (o que a comanda É, e a porta "Comanda ⋯"), a lista,
// o bloco de ação (o objeto em foco) e o pé (Enviar · Transferir · Pagamento). O que
// muda é o OBJETO em foco: a comanda, uma linha aberta ou várias linhas marcadas.
//
// MARCAR NÃO É MODO, E A MARCA É LITERAL (dono, 13/10/2026): a caixa clicada é a caixa
// marcada, no mesmo toque. Uma marca é uma marca (o bloco das marcadas com 1); a linha
// aberta no editor é outra coisa (o foco da quantidade) e não entra na conta sozinha.
// Desmarcar a última volta ao editor da linha aberta. Este módulo é a regra pura disso;
// a tela só desenha.
import type { POSCartItem } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";
import { lineTotalQ } from "~/presentation/lineDiscounts";
import { countUnits } from "~/presentation/selection";
import { isWeighedLine } from "~/presentation/weighed";

/**
 * Marcar ou desmarcar UMA linha: só ela muda, nada mais entra junto. Já houve uma regra
 * que juntava a linha aberta como "primeira marcada" e transformava conjunto de um em
 * linha aberta; a caixa clicada ficava vazia e o operador clicava de novo sem saber se
 * tinha aceitado (dono, 13/10/2026).
 */
export function toggleMark(marked: ReadonlySet<string>, lineId: string): Set<string> {
  const next = new Set(marked);
  if (next.has(lineId)) next.delete(lineId);
  else next.add(lineId);
  return next;
}

/** Shift + clique: marca o intervalo entre a âncora (a última marcada, ou a linha aberta) e esta. */
export function markRange(
  items: readonly POSCartItem[],
  marked: ReadonlySet<string>,
  anchorId: string,
  lineId: string,
): Set<string> {
  const ids = items.map((item) => item.line_id);
  const from = ids.indexOf(anchorId);
  const to = ids.indexOf(lineId);
  if (from < 0 || to < 0) return toggleMark(marked, lineId);
  const next = new Set(marked);
  const [start, end] = from < to ? [from, to] : [to, from];
  for (let index = start; index <= end; index += 1) next.add(ids[index]!);
  return next;
}

export interface MarkedSummary {
  lines: number;
  units: number;
  totalQ: number;
  /** "5 itens marcados": o objeto do bloco, em ITENS (a grandeza da casa, nunca linhas). */
  headline: string;
  /** O valor das marcadas, ao lado do título. */
  totalDisplay: string;
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
    headline: units === 1 ? "1 item marcado" : `${units} itens marcados`,
    totalDisplay: formatBRL(totalQ),
    hasWeighed: chosen.some((item) => isWeighedLine(item)),
  };
}

export interface FireCellInput {
  /** Itens a enviar na comanda inteira (o `fireBarView`). */
  unfired: number;
  /** O rótulo do servidor para enviar ("Enviar à cozinha") ou o estado ("Enviado"). */
  label: string;
  disabled: boolean;
  /** Linhas marcadas (1 ou mais) e, delas, as que ainda não foram à cozinha. */
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
  if (input.markedLines >= 1) {
    const n = input.markedFirable;
    if (!n) {
      return {
        label: "Marcados já na cozinha",
        shortLabel: "Na cozinha",
        count: 0,
        disabled: true,
        title: "Os itens marcados já estão na cozinha",
        onlyMarked: true,
      };
    }
    // O título do bloco já diz quantos; o botão diz o alcance ("os marcados"), e a dica
    // avisa quando parte deles já foi.
    return {
      label: "Enviar marcados",
      shortLabel: "Enviar",
      count: 0,
      disabled: input.disabled || input.offline,
      title: input.offline
        ? "Cozinha sem conexão: avise de voz"
        : n < input.markedLines
          ? "Enviar à cozinha os marcados que ainda não foram (F9)"
          : "Enviar à cozinha só os marcados (F9)",
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
}

/**
 * O estado da cozinha em palavra: o que falta e o que já foi. O modo do envio (Auto ·
 * Manual) é um controle no cabeçalho (dono, 13/10/2026), não uma frase; sem conexão, o
 * cabeçalho diz o motivo ao lado.
 */
export function kitchenStateView(args: { unfired: number; fired: number }): KitchenStateView {
  const parts: string[] = [];
  if (args.unfired) parts.push(`${args.unfired} a enviar`);
  if (args.fired) parts.push(`${args.fired} na cozinha`);
  return { counts: parts.join(" · ") };
}
