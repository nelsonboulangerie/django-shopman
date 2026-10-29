import type { CatalogItemProjection, ProductDetailProjection, ProductRecommendationsProjection, ProductNutritionProjection } from '~/types/shopman'

// Transforms puros da PDP: descrição sem eco, tabela nutricional com %VD e
// a lista "Veja também" (cross_sell por keywords compartilhadas).

export type NutritionTableRow = {
  label: string
  value: string
  pdv: number | null
}

export type NutritionTable = {
  serving: string
  rows: NutritionTableRow[]
}

// Disponibilidade na loja física: o Google só mostra "retirada hoje" quando a
// página do produto diz que o item está na loja. Só para estoque PRONTO hoje;
// produção planejada ainda não está na prateleira e não promete retirada.
export function inStorePickupLine (product: Pick<ProductDetailProjection, 'availability' | 'can_add_to_cart'>): string {
  if (!product.can_add_to_cart) return ''
  if (product.availability !== 'available' && product.availability !== 'low_stock') return ''
  return 'Disponível hoje na loja, com retirada grátis.'
}

export function detailDescription (product: Pick<ProductDetailProjection, 'short_description' | 'long_description'>): string {
  if (!product.long_description) return ''
  return product.long_description === product.short_description ? '' : product.long_description
}

export function nutritionTable (nutrition: ProductNutritionProjection | null): NutritionTable | null {
  if (!nutrition || !nutrition.rows.length) {
    if (!nutrition?.energy_kcal_display) return null
  }
  const rows: NutritionTableRow[] = []
  if (nutrition?.energy_kcal_display) {
    rows.push({ label: 'Valor energético', value: nutrition.energy_kcal_display, pdv: nutrition.energy_pdv })
  }
  for (const row of nutrition?.rows || []) {
    rows.push({ label: row.label, value: row.value_display, pdv: row.percent_daily_value })
  }
  if (!rows.length) return null
  return { serving: nutrition?.serving_size_display || '', rows }
}

// Miniaturas da galeria: a foto principal entra primeiro, seguida das adicionais
// de `gallery`, sem repetição. Lista vazia = produto de foto única, sem carrossel.
export function galleryImages (product: Pick<ProductDetailProjection, 'image_url' | 'gallery'>): string[] {
  const urls = [product.image_url, ...(product.gallery || [])].filter((url): url is string => Boolean(url))
  const unique = [...new Set(urls)]
  return unique.length > 1 ? unique : []
}

// O rail mostra no máximo quatro cards: o servidor corta em 4 e o cliente corta
// de novo aqui. O número é UM só porque o placeholder de carregamento reserva
// exatamente essa altura: se o teto subir no servidor, a reserva sobe junto.
export const CROSS_SELL_LIMIT = 4

// Quanto a seção de sugestões antecipa a leitura antes de entrar na viewport.
//
// 0px é o contrato literal: o request parte quando a seção aparece, não antes.
// Com 240px (o valor anterior) o pedido partia entre 1,07 s e 1,73 s com
// scrollY=0 numa viewport de 390x844: o "lazy" não adiava nada no mobile e a
// PDP pagava dois TTFB em série (~0,78 s do SSR + ~0,72 s do rail). Folga maior
// não compra nada aqui: o rail fica no pé da página, depois do conteúdo que
// decide a compra (preço, opções, adicionar), e a reserva de altura já evita o
// pulo enquanto a resposta não chega.
export const RECOMMENDATIONS_ROOT_MARGIN = '0px'

export function crossSellItems (product: Pick<ProductRecommendationsProjection, 'items' | 'sku'>, limit = CROSS_SELL_LIMIT): CatalogItemProjection[] {
  return (product.items || [])
    .filter(item => item.sku !== product.sku)
    .slice(0, limit)
}
