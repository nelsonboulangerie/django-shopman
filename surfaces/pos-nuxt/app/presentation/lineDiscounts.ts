// Presentation — transparência de desconto por linha (o caso Batard R$ 13,00 → R$ 11,05).
//
// O kernel carimba na linha o desconto automático vencedor (lote/liquidação,
// happy hour, funcionário) e o payload da comanda o expõe como
// `pricing_discount` (tipo + rótulo de cliente + valor). Aqui vive só a DECISÃO
// de badge: preferir o percentual ("Liquidação −15%") e cair no valor em R$
// quando o percentual não fecha limpo. É o mesmo idioma visual da tela do
// cliente (/display), que delega para cá — preço nunca muda calado.

import type { POSCartItem, POSCheckoutOptionProjection } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";

/** "Liquidação −15%" (ou "Liquidação −R$ 1,95"). "" quando não há desconto automático. */
export function pricingDiscountBadge(item: POSCartItem): string {
  const disc = item.pricing_discount;
  if (!disc || !disc.amount_q || disc.amount_q <= 0) return "";
  const label = disc.label || "Desconto";
  return disc.percent > 0 ? `${label} −${disc.percent}%` : `${label} −${formatBRL(disc.amount_q)}`;
}

/** Rótulo do desconto MANUAL da linha: "Cortesia −10%". "" quando não há. */
export function manualDiscountLabel(
  item: POSCartItem,
  reasons: POSCheckoutOptionProjection[],
): string {
  const pct = item.discount?.value || 0;
  if (pct <= 0) return "";
  const reasonRef = item.discount?.reason || "";
  const label = reasons.find((option) => option.ref === reasonRef)?.label || reasonRef || "Desconto";
  return `${label} −${pct}%`;
}

/** O badge da linha: o desconto automático vence a exibição (é o que mexeu no preço). */
export function lineDiscountBadge(
  item: POSCartItem,
  reasons: POSCheckoutOptionProjection[] = [],
): string {
  return pricingDiscountBadge(item) || manualDiscountLabel(item, reasons);
}

export interface SaleDiscountBadge {
  sku: string;
  name: string;
  badge: string;
}

/** Uma linha por item com desconto (automático ou manual) — o resumo do checkout. */
export function saleDiscountBadges(
  items: POSCartItem[],
  reasons: POSCheckoutOptionProjection[] = [],
): SaleDiscountBadge[] {
  const rows: SaleDiscountBadge[] = [];
  for (const item of items) {
    const badge = lineDiscountBadge(item, reasons);
    if (badge) rows.push({ sku: item.sku, name: item.name, badge });
  }
  return rows;
}
