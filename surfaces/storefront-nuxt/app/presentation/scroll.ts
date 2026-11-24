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

// A RÉGUA DO PRÓXIMO FOCO DEPENDE DE ONDE A PÁGINA PARA (#3477).
//
// A régua CSS (`[data-focus-target]`, 4rem + 6px) é a base da navbar com a status
// bar já recolhida. Só que a status bar recolhe pela ROLAGEM: quando o bloco de
// foco mora perto do topo, levá-lo à régua para a página numa rolagem que não
// passa do limiar de colapso, a status bar continua de pé e cobre os 36px de cima
// do bloco. Foi o título do /entrar no celular: rolagem 54, título em 70,
// cabeçalho até 106.
//
// A folga devolvida aqui é o quanto a régua desce para quem vai parar nessa faixa.
// Fecha nos dois estados de partida:
// - parada depois do limiar de colapso: a status bar recolhe agora ou já estava
//   recolhida (e fica, pois passou da reexpansão); a régua base é a certa;
// - parada antes: mirar 36px mais alto deixa a rolagem no máximo na reexpansão,
//   então a status bar fica (ou volta) de pé e o bloco encosta na base dela. No
//   único ponto em que ela pode seguir recolhida (exatamente na reexpansão), o
//   bloco só fica 36px abaixo da navbar: à vista, nunca coberto.
export function focusRulerAllowance (landingScrollY: number): number {
  return landingScrollY > HEADER_COLLAPSE_AT ? 0 : STATUS_BAR_HEIGHT
}
