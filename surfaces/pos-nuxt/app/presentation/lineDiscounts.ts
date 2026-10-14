// Presentation — transparência de desconto por linha (o caso Batard R$ 13,00 → R$ 11,05).
//
// O kernel carimba na linha o desconto automático vencedor (lote/liquidação,
// happy hour, funcionário) e o payload da comanda o expõe como
// `pricing_discount` (tipo + rótulo de cliente + valor). Aqui vive só a DECISÃO
// de badge: preferir o percentual ("Liquidação −15%") e cair no valor em R$
// quando o percentual não fecha limpo. É o mesmo idioma visual da tela do
// cliente (/display), que delega para cá — preço nunca muda calado.

import type { POSCartItem } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";
import { lineAmountQ } from "~/presentation/weighed";

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

/** Quanto o desconto MANUAL desta linha tira por unidade, em centavos.
 *
 *  A mesma conta do kernel (`DiscountModifier._calc_manual`) e da review
 *  (`_payload_line_discounts_q`): percentual sobre a ETIQUETA, ou o valor em
 *  reais direto — e nunca mais do que a etiqueta inteira.
 */
export function manualDiscountPerUnitQ(item: POSCartItem): number {
  const value = item.discount?.value || 0;
  if (value <= 0) return 0;
  const listQ = typeof item.list_price_q === "number" ? item.list_price_q : unitChargedQ(item);
  const asked = item.discount?.type === "fixed"
    ? Math.round(value * 100)
    : Math.round((listQ * value) / 100);
  return Math.min(asked, listQ);
}

/** O desconto manual desta linha foi DESCARTADO pelo servidor?
 *
 *  A política é "maior desconto ganha, um por item": uma cortesia de 10% numa
 *  linha que já levou "Semana do Pão −15%" não vale.
 *
 *  ⚠️ Isto era um CHUTE — "tem automático carimbado e o operador pediu manual,
 *  logo o manual perdeu". A heurística acertava por acidente enquanto o manual
 *  só existia em percentuais pequenos, e passou a errar assim que ele aceitou
 *  reais: R$ 2,50 numa Tabatière que levava "Semana do Pão −15%" (R$ 0,90)
 *  GANHA, e o operador ouvia que o desconto dele não valeu. Agora os dois lados
 *  são medidos, com a régua do kernel.
 *
 *  Isto NÃO vira selo na linha: a linha mostra só o vencedor. Vira o aviso do
 *  MOMENTO em que o operador pede o desconto — feedback onde a ação acontece,
 *  em vez de um selo riscado morando ali para sempre.
 */
export function manualDiscountWasOverridden(item: POSCartItem): boolean {
  const autoPerUnitQ = item.pricing_discount?.label ? lineListUnitQ(item) - unitChargedQ(item) : 0;
  if (autoPerUnitQ <= 0) return false;
  return manualDiscountPerUnitQ(item) <= autoPerUnitQ;
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

/** O que a linha cobra por unidade, segundo o servidor, no eco de cada gravação. */
export type POSLinePrice = Pick<POSCartItem, "charged_price_q" | "list_price_q" | "pricing_discount">;

/** O preço por unidade que a linha passa a cobrar com o desconto manual que ela
 *  tem AGORA, pela régua do kernel: etiqueta menos o MAIOR entre o manual e o
 *  automático conhecido (um desconto por item, o maior ganha).
 *
 *  É a resposta instantânea do toque em Aplicar. Sem ela, o total da linha
 *  esperava o servidor, e o servidor só o devolvia ao reabrir a comanda: o dono
 *  deu R$ 1,00 numa linha e o total só mudou quando recarregou a página
 *  (13/10/2026). O eco da gravação (`applyLinePrices`) confirma logo depois.
 *
 *  O automático conhecido é o que venceu a linha (`pricing_discount`). Um
 *  automático que o manual anterior tinha batido não aparece aqui; nesse caso
 *  raro o eco corrige o número em seguida.
 */
export function manualDiscountChargedQ(item: POSCartItem): number {
  const listQ = lineListUnitQ(item);
  const autoQ = Math.max(0, item.pricing_discount?.amount_q || 0);
  return Math.max(0, listQ - Math.max(manualDiscountPerUnitQ(item), autoQ));
}

/** Aplica o preço que o servidor diz que cada linha cobra (eco do salvar).
 *  Só escreve o que mudou: cada escrita na linha reagenda a gravação. */
export function applyLinePrices(
  items: POSCartItem[],
  linePrices: Record<string, POSLinePrice> | undefined | null,
): void {
  if (!linePrices) return;
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
  }
}

/** As linhas SEM o eco de preço do servidor, para a chave que decide rever o total.
 *
 *  A revisão da venda sem comanda devolve o que cada linha cobra (o desconto do
 *  grupo do cliente, a Xepa) e a tela grava isso na linha. Se esses campos
 *  entrassem na chave, gravar o eco pediria outra revisão, e a tela voltaria a
 *  dizer "Calculando…" depois de cada resposta. Eles não mudam o total: é o
 *  servidor que os calcula a partir do resto da linha.
 */
export function linesWithoutServerPrices(items: readonly POSCartItem[]): Array<Partial<POSCartItem>> {
  return items.map(({ charged_price_q: _charged, list_price_q: _list, pricing_discount: _auto, ...rest }) => rest);
}
