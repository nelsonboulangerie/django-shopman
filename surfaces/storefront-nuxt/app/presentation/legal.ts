// Documento legal — as regras puras que a moldura (`LegalDocument`) e o resumo
// (`LegalSummary`) dividem. Sem DOM, sem Vue além das chaves de injeção.
import type { ComputedRef, InjectionKey } from 'vue'

export type LegalSummaryVariant = 'list' | 'essentials'

/** Número da seção (1, 2, …) pela âncora, na ordem em que as seções aparecem. */
export type LegalSectionNumber = (anchor: string) => number | null

export const legalSectionNumberKey: InjectionKey<LegalSectionNumber> = Symbol('legal-section-number')
/** O salto até a seção, pelo próximo foco (o mesmo do índice). */
export const legalGoToKey: InjectionKey<(anchor: string) => void> = Symbol('legal-go-to')
export const legalSummaryVariantKey: InjectionKey<ComputedRef<LegalSummaryVariant>> = Symbol('legal-summary-variant')

/**
 * `#sharing` → 4, dada a ordem das seções. Âncora que não existe devolve `null`:
 * o item do resumo que aponta para uma seção inexistente é um defeito, e a
 * trava em tests/legalDocument.test.ts reprova antes de chegar à tela.
 */
export function sectionNumber (orderedIds: readonly string[], anchor: string): number | null {
  const index = orderedIds.indexOf(anchor.replace(/^#/, ''))
  return index === -1 ? null : index + 1
}
