// Colapso da status bar do header ao rolar.
//
// O colapso NÃO pode mexer na altura do documento. Quando mexia, o header
// realimentava a própria entrada: encolher a página faz o browser corrigir o
// `scrollY` sozinho — por clamp (a folga de rolagem sumiu) ou por scroll
// anchoring (`overflow-anchor: auto`, o padrão), que desloca a rolagem pela
// altura exata da barra para manter o conteúdo no lugar. O scroll corrigido
// dispara um novo evento, o handler reavalia, e a barra oscila para sempre.
//
// Isso foi medido no alpha: colapsar a barra movia o scroll de 200 para 164,
// 36px = a altura da barra. Limiar único tremia perto de 8px; com histerese de
// 20px o laço encolheu para a faixa em que o salto de 36px pula os dois
// limiares (rolagem parada entre 36 e 40), mas continuou existindo. Nenhum par
// de limiares resolve: o salto é do tamanho da barra, e zona morta menor que
// isso sempre pode ser atravessada.
//
// Por isso o header mantém altura CONSTANTE no fluxo e o colapso vira
// `translateY` (fora do fluxo, sem relayout). Sem mudança de altura não há
// clamp nem anchoring, e a histerese abaixo passa a ser só defesa em
// profundidade — barata e já testada.

// Altura da status bar (`h-9` = 2.25rem = 36px), que é o quanto o header
// desliza para cima ao colapsar.
export const STATUS_BAR_HEIGHT = 36

// Enquanto colapsado o header aparece 36px mais alto do que ocupa no fluxo, e
// o conteúdo só fica coberto pela navbar a partir de `scrollY >= 36`. Reexpandir
// exatamente na altura da barra garante o invariante "colapsado ⇒ o conteúdo já
// passou por baixo da navbar", sem faixa de fundo aparecendo sob ela.
export const HEADER_EXPAND_AT = STATUS_BAR_HEIGHT

// A zona morta é no mínimo a altura da barra. Assim, se ainda sobrar qualquer
// correção de scroll do tamanho dela, a correção não alcança o outro limiar e o
// estado assenta. Zona morta menor NÃO basta: com 20px (a versão anterior) o
// salto de 36px pulava os dois limiares e a barra oscilava para sempre.
export const HEADER_COLLAPSE_AT = HEADER_EXPAND_AT + STATUS_BAR_HEIGHT

export function headerCollapsed (collapsed: boolean, scrollY: number): boolean {
  if (collapsed) return scrollY >= HEADER_EXPAND_AT
  return scrollY > HEADER_COLLAPSE_AT
}
