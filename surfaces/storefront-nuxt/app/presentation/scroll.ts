// Colapso da status bar do header ao rolar. Um limiar único oscila: colapsar a
// barra encurta o documento, o browser clampa o scroll de volta para trás do
// limiar, a barra reexpande e o laço recomeça (tremor de ~1px com a rolagem
// parada no limiar — pego pelo E2E como "element is not stable"). A histerese
// quebra o laço: colapsa bem depois do topo e só reexpande de volta ao topo,
// então o recuo causado pelo próprio colapso cai na zona morta e o estado fica.
export const HEADER_COLLAPSE_AT = 24
export const HEADER_EXPAND_AT = 4

export function headerCollapsed (collapsed: boolean, scrollY: number): boolean {
  if (collapsed) return scrollY >= HEADER_EXPAND_AT
  return scrollY > HEADER_COLLAPSE_AT
}
