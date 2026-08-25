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

/** Rótulo do desconto MANUAL da linha: "Cortesia −10%". "" quando não há. */
export function manualDiscountLabel(
  item: POSCartItem,
  reasons: readonly DiscountReasonOption[],
): string {
  const pct = item.discount?.value || 0;
  if (pct <= 0) return "";
  const reasonRef = item.discount?.reason || "";
  const label = reasons.find((option) => option.ref === reasonRef)?.label || reasonRef || "Desconto";
  return `${label} −${pct}%`;
}

/** O desconto manual desta linha foi DESCARTADO pelo servidor?
 *
 *  A política é "maior desconto ganha, um por item": uma cortesia de 10% numa
 *  linha que já levou "Semana do Pão −15%" não vale. Quem decide é o carimbo do
 *  servidor — `pricing_discount` só existe quando um desconto AUTOMÁTICO venceu
 *  a linha (o tipo "manual" fica fora daquele conjunto). Logo, automático
 *  presente + manual pedido ⇒ o manual perdeu.
 *
 *  Isto NÃO vira selo na linha: a linha mostra só o vencedor. Vira o aviso do
 *  MOMENTO em que o operador pede o desconto — feedback onde a ação acontece,
 *  em vez de um selo riscado morando ali para sempre.
 */
export function manualDiscountWasOverridden(item: POSCartItem): boolean {
  return Boolean(item.discount?.value && item.pricing_discount?.label);
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
  return unitChargedQ(item) * item.qty;
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
  return typeof item.list_price_q === "number" ? item.list_price_q * item.qty : 0;
}

/** Quanto esta linha economizou, em centavos. 0 quando não houve desconto. */
export function lineSavingsQ(item: POSCartItem): number {
  return Math.max(0, lineListTotalQ(item) - lineTotalQ(item));
}

export interface SaleDiscountBadge {
  sku: string;
  name: string;
  badge: string;
}

/** Uma linha por item com desconto (automático ou manual) — o resumo do checkout. */
export function saleDiscountBadges(
  items: POSCartItem[],
  reasons: readonly DiscountReasonOption[] = [],
): SaleDiscountBadge[] {
  const rows: SaleDiscountBadge[] = [];
  for (const item of items) {
    const badge = lineDiscountBadge(item, reasons);
    if (badge) rows.push({ sku: item.sku, name: item.name, badge });
  }
  return rows;
}
