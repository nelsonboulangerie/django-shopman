import { formatCentavos } from '~/presentation/cart'
import type { PriceAdjustment, PriceQuote } from '~/types/shopman'

export function quotePriceDisplay (quote: PriceQuote): string {
  return quote.final_unit_price_q > 0 ? formatCentavos(quote.final_unit_price_q) : ''
}

export function quoteOriginalPriceDisplay (quote: PriceQuote): string | null {
  return quote.final_unit_price_q < quote.list_unit_price_q
    ? formatCentavos(quote.list_unit_price_q)
    : null
}

// Selo da promoção: o nome dela junto do número ("Semana do Pão -15%"). Só o
// "-15%" deixava o cliente sem saber de onde vinha o desconto, e a sacola chama
// a promoção pelo nome (beta 06/11).
export function adjustmentLabel (adjustment: Pick<PriceAdjustment, 'label' | 'badge_label'>): string {
  const name = adjustment.label?.trim() || ''
  const badge = adjustment.badge_label?.trim() || ''
  if (name && badge && name !== badge) return `${name} ${badge}`
  return badge || name
}
