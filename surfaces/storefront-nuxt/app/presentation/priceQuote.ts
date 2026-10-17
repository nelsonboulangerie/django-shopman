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

export function adjustmentLabel (adjustment: PriceAdjustment): string {
  return adjustment.badge_label || adjustment.label
}
