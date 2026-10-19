// Presentation — transparência de desconto por linha (o caso Batard R$ 13,00 → R$ 11,05).
//
// O kernel carimba na linha o desconto automático vencedor (lote/liquidação,
// happy hour, grupo de clientes) e o payload da comanda o expõe como
// `pricing_discount` (tipo + rótulo de cliente + valor). Aqui vive só a DECISÃO
// de badge: preferir o percentual ("Liquidação −15%") e cair no valor em R$
// quando o percentual não fecha limpo. É o mesmo idioma visual da tela do
// cliente (/display), que delega para cá — preço nunca muda calado.

import type { POSCartItem } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";
import { isWeighedLine, lineAmountQ } from "~/presentation/weighed";

/** "Liquidação −15%" (ou "Liquidação −R$ 1,95"). "" quando não há desconto automático. */
export function pricingDiscountBadge(item: POSCartItem): string {
  const disc = item.pricing_discount;
  if (!disc || !disc.amount_q || disc.amount_q <= 0) return "";
  const label = disc.label || "Desconto";
  return disc.percent > 0 ? `${label} −${disc.percent}%` : `${label} −${formatBRL(disc.amount_q)}`;
}

/** A lista de motivos que estas funções realmente usam: um `ref` e um rótulo.
 *  Mais estreita que a projection de opções do checkout de propósito — o painel do
 *  carrinho normaliza a lista do servidor e cai nos motivos padrão, que não têm
 *  `description`, e exigir o campo forçaria inventar um vazio só para o tipo. */
export type DiscountReasonOption = { ref: string; label?: string };

/** Rótulo do desconto MANUAL da linha: "Cortesia −10%" ou "Cortesia −R$ 2,00".
 *  "" quando não há. O formato do rótulo segue o formato que o operador digitou;
 *  traduzir um para o outro esconderia o gesto que ele fez. */
export function manualDiscountLabel(
  item: POSCartItem,
  reasons: readonly DiscountReasonOption[],
): string {
  const value = item.discount?.value || 0;
  if (value <= 0) return "";
  const reasonRef = item.discount?.reason || "";
  const label = reasons.find((option) => option.ref === reasonRef)?.label || reasonRef || "Desconto";
  const amount = item.discount?.type === "fixed" ? formatBRL(Math.round(value * 100)) : `${value}%`;
  return `${label} −${amount}`;
}

/** A etiqueta por UNIDADE. Cai no cobrado quando o servidor não disse. */
export function lineListUnitQ(item: POSCartItem): number {
  return typeof item.list_price_q === "number" ? item.list_price_q : unitChargedQ(item);
}

/** O rótulo do desconto que VENCEU a linha, para o aviso. "" quando não há. */
export function winningDiscountLabel(item: POSCartItem): string {
  return item.pricing_discount?.label || "";
}

/** O badge da linha: o desconto automático vence a exibição (é o que mexeu no preço). */
export function lineDiscountBadge(
  item: POSCartItem,
  reasons: readonly DiscountReasonOption[] = [],
): string {
  return pricingDiscountBadge(item) || manualDiscountLabel(item, reasons);
}

/** O total da LINHA: preço unitário do SERVIDOR × a quantidade da TELA.
 *
 *  ⚠️ `qty × price_q` não serve: `price_q` é o preço de RESTAURAÇÃO
 *  (pré-desconto manual), maior do que o cliente paga.
 *
 *  ⚠️ E o servidor NÃO manda o total da linha pronto, embora seja trivial para
 *  ele: a quantidade muda de forma otimista no cliente e só depois vai ao
 *  servidor, então entre o "+" e a resposta um total vindo pronto fica
 *  congelado — cheguei a ver na tela um item com qty 123 exibindo o total de 2.
 *  A divisão honesta é esta: o PREÇO é política (servidor), a QUANTIDADE é o que
 *  o dedo acabou de fazer (tela). Multiplicar os dois não é calcular política.
 */
export function lineTotalQ(item: POSCartItem): number {
  // Na linha pesada, `peso × preço do quilo` arredondado como o kernel — nunca
  // `preço × 0,312`, que dá fração de centavo.
  return lineAmountQ(unitChargedQ(item), item);
}

/** O que se cobra por UNIDADE. Mesma armadilha do total: `price_q` é restauração. */
export function unitChargedQ(item: POSCartItem): number {
  if (typeof item.charged_price_q === "number") return item.charged_price_q;
  return item.price_q;
}

/** A etiqueta RISCADA da linha: o total que ela teria sem desconto nenhum.
 *  "" quando não há diferença — riscar um número igual ao cobrado é ruído. */
export function lineListTotalDisplay(item: POSCartItem): string {
  const list = lineListTotalQ(item);
  if (!list || list <= lineTotalQ(item)) return "";
  return formatBRL(list);
}

/** O total de etiqueta da linha, em centavos. 0 quando o servidor não disse. */
export function lineListTotalQ(item: POSCartItem): number {
  return typeof item.list_price_q === "number" ? lineAmountQ(item.list_price_q, item) : 0;
}

/** Quanto esta linha economizou, em centavos. 0 quando não houve desconto. */
export function lineSavingsQ(item: POSCartItem): number {
  return Math.max(0, lineListTotalQ(item) - lineTotalQ(item));
}

/** O que a linha cobra por unidade, segundo o servidor, no eco de cada gravação
 *  e na revisão. `manual_discount_discarded`: o motor descartou o desconto que o
 *  operador deu nesta linha, porque o automático dela é maior ("maior desconto
 *  ganha, um por item"). Quem decide é o motor; a tela só repete. */
export type POSLinePrice = Pick<POSCartItem, "charged_price_q" | "list_price_q" | "pricing_discount"> & {
  manual_discount_discarded?: boolean;
};

/** Aplica o preço que o servidor diz que cada linha cobra (eco do salvar ou da
 *  revisão) e tira da linha o "calculando". Só escreve o que mudou: cada escrita
 *  na linha reagenda a gravação.
 *
 *  Devolve as linhas em que o motor DESCARTOU o desconto manual, para quem pediu
 *  o desconto dizer isso ao operador no momento do pedido. */
export function applyLinePrices(
  items: POSCartItem[],
  linePrices: Record<string, POSLinePrice> | undefined | null,
): string[] {
  const discarded: string[] = [];
  if (!linePrices) return discarded;
  for (const item of items) {
    const price = linePrices[item.line_id];
    if (!price) continue;
    if (typeof price.charged_price_q === "number" && item.charged_price_q !== price.charged_price_q) {
      item.charged_price_q = price.charged_price_q;
    }
    if (typeof price.list_price_q === "number" && item.list_price_q !== price.list_price_q) {
      item.list_price_q = price.list_price_q;
    }
    const next = price.pricing_discount ?? null;
    if (JSON.stringify(item.pricing_discount ?? null) !== JSON.stringify(next)) {
      item.pricing_discount = next;
    }
    if (item.price_pending) item.price_pending = false;
    if (price.manual_discount_discarded) discarded.push(item.line_id);
  }
  return discarded;
}

/** As linhas SEM o eco de preço do servidor, para a chave que decide rever o total.
 *
 *  A revisão devolve o que cada linha cobra (o desconto do grupo do cliente, a
 *  Xepa, o desconto manual decidido pelo motor) e a tela grava isso na linha. Se
 *  esses campos entrassem na chave, gravar o eco pediria outra revisão, e a tela
 *  voltaria a dizer "Calculando…" depois de cada resposta. Eles não mudam o
 *  total: é o servidor que os calcula a partir do resto da linha. O
 *  `price_pending` é o estado de espera desse eco, e fica fora pelo mesmo motivo.
 */
export function linesWithoutServerPrices(items: readonly POSCartItem[]): Array<Partial<POSCartItem>> {
  return items.map(({
    charged_price_q: _charged, list_price_q: _list, pricing_discount: _auto, price_pending: _pending, ...rest
  }) => rest);
}

/** O alcance de um desconto de linha: quanto ele tira por unidade e na linha. */
export type DiscountReach = {
  /** Quanto sai de CADA unidade, em centavos. */
  perUnitQ: number;
  /** Quanto sai da linha inteira, em centavos. */
  lineQ: number;
  /** O percentual, quando o desconto foi dado em %. `null` quando foi em R$. */
  percent: number | null;
  /** A linha tem mais de uma unidade (a peça pesada nunca tem). */
  multiUnit: boolean;
};

function percentText(percent: number): string {
  return `${String(Math.round(percent * 100) / 100).replace(".", ",")}%`;
}

/** O alcance dito por extenso, pela régua do kernel (`_calc_manual`: o desconto em
 *  R$ é POR UNIDADE).
 *
 *  Em R$ numa linha de 3: "R$ 1,00 por unidade · R$ 3,00 na linha". Sem isso o
 *  operador lia "R$ 1,00" e esperava R$ 1,00 a menos na linha (dono, 14/10/2026).
 *  Em %: "10% · R$ 2,07 na linha", porque percentual sozinho não diz quanto saiu.
 *  Em R$ numa linha de 1, o valor basta: por unidade e na linha são o mesmo número.
 *  `sign` é o "−" do selo; o editor fala sem ele (ali o assunto já é o desconto).
 */
export function discountReachText(reach: DiscountReach, sign = ""): string {
  if (reach.perUnitQ <= 0) return "";
  if (reach.percent !== null && reach.percent > 0) {
    return `${sign}${percentText(reach.percent)} · ${sign}${formatBRL(reach.lineQ)} na linha`;
  }
  if (!reach.multiUnit) return `${sign}${formatBRL(reach.perUnitQ)}`;
  return `${sign}${formatBRL(reach.perUnitQ)} por unidade · ${sign}${formatBRL(reach.lineQ)} na linha`;
}

/** Quanto sai da linha quando cada unidade perde `perUnitQ`, com o arredondamento
 *  da peça pesada (o kernel multiplica o preço já descontado pelo peso). */
function lineReachQ(listQ: number, perUnitQ: number, item: Pick<POSCartItem, "qty" | "weighed">): number {
  return Math.max(0, lineAmountQ(listQ, item) - lineAmountQ(listQ - perUnitQ, item));
}

/** O alcance do desconto que VENCEU a linha, medido no que o servidor cobra.
 *  O mesmo vencedor do selo (`lineDiscountBadge`): o automático, se houver, senão o
 *  manual. `null` quando a linha não tem desconto, ou quando o servidor ainda não
 *  disse o preço da linha (`price_pending`): a tela não faz a conta do motor. */
export function lineDiscountReach(item: POSCartItem): DiscountReach | null {
  const auto = pricingDiscountBadge(item) ? item.pricing_discount! : null;
  const manual = (item.discount?.value || 0) > 0;
  if ((!auto && !manual) || item.price_pending) return null;
  const listQ = lineListUnitQ(item);
  const measuredQ = typeof item.list_price_q === "number" ? listQ - unitChargedQ(item) : 0;
  const perUnitQ = measuredQ > 0 ? measuredQ : auto ? Math.max(0, auto.amount_q) : 0;
  if (perUnitQ <= 0) return null;
  const percent = auto
    ? auto.percent > 0 ? auto.percent : null
    : item.discount?.type === "fixed" ? null : item.discount?.value || null;
  const savedQ = lineSavingsQ(item);
  return {
    perUnitQ,
    lineQ: savedQ > 0 ? savedQ : lineReachQ(listQ, perUnitQ, item),
    percent,
    multiUnit: !isWeighedLine(item) && item.qty > 1,
  };
}

/** O selo da linha, sem o motivo: "−R$ 1,00 por unidade · −R$ 3,00 na linha". */
export function lineDiscountFact(item: POSCartItem): string {
  const reach = lineDiscountReach(item);
  return reach ? discountReachText(reach, "−") : "";
}

/** O detalhe da linha, com o motivo: "Cortesia −R$ 1,00 por unidade · −R$ 3,00 na linha". */
export function lineDiscountDetail(item: POSCartItem, reasons: readonly DiscountReasonOption[] = []): string {
  const fact = lineDiscountFact(item);
  if (!fact) return "";
  const label = pricingDiscountBadge(item)
    ? item.pricing_discount?.label || "Desconto"
    : reasons.find((option) => option.ref === item.discount?.reason)?.label || item.discount?.reason || "Desconto";
  return `${label} ${fact}`;
}

/** A pergunta da prévia ao servidor e a resposta dela: o desconto que o operador
 *  está digitando nesta linha, e o preço que a revisão deu à linha com ele. */
export type DiscountPreview = {
  lineId: string;
  kind: "percent" | "fixed";
  value: number;
  status: "pending" | "ready" | "failed";
  price?: POSLinePrice;
};

/** O que a prévia do editor de desconto mostra antes do Aplicar. */
export type DraftDiscountOutcome =
  | { kind: "reach"; reach: DiscountReach }
  /** O motor descartaria o desconto digitado: o automático da linha é maior. */
  | { kind: "discarded"; winner: string };

/** O alcance do desconto que o operador está DIGITANDO, segundo a REVISÃO do
 *  servidor com esse desconto na linha (o motor decide, a tela não conta).
 *  `price` é o preço da linha que a revisão devolveu. `null` sem valor. */
export function draftDiscountOutcome(
  item: POSCartItem,
  kind: "percent" | "fixed",
  value: number,
  price: POSLinePrice,
): DraftDiscountOutcome | null {
  if (!(value > 0)) return null;
  if (price.manual_discount_discarded) {
    return { kind: "discarded", winner: price.pricing_discount?.label || "Outro desconto" };
  }
  if (typeof price.list_price_q !== "number" || typeof price.charged_price_q !== "number") return null;
  const perUnitQ = price.list_price_q - price.charged_price_q;
  if (perUnitQ <= 0) return null;
  return {
    kind: "reach",
    reach: {
      perUnitQ,
      lineQ: lineReachQ(price.list_price_q, perUnitQ, item),
      percent: kind === "percent" ? value : null,
      multiUnit: !isWeighedLine(item) && item.qty > 1,
    },
  };
}
