// Cartão de ação preso na base (`.shop-action-dock`, #3573): só flutua enquanto cabe.
//
// No celular o cartão do total (sacola, finalizar) fica fixo acima da navegação inferior.
// Com a fonte do sistema a 200 % ele cresce junto com o texto, e a soma de cabeçalho
// fixo, cartão e navegação passa a tomar quase toda a tela. Medido em 375x812 com a
// fonte a 200 % (antes do conserto): cabeçalho 134 px no alto, cartão de 234 a 266 px
// e 160 px dele até a base (navegação e folga); sobravam de 252 a 284 px de conteúdo
// (31 % a 35 % da tela), e o que a página leva ao meio da tela (o item da sacola, o
// preço, "Remover", "Editar") ficava atrás do cartão. A 320 px o cartão chega a 276 px.
//
// A regra: o cartão fixo precisa deixar pelo menos MIN_CONTENT_SHARE da altura da tela
// para o conteúdo, entre o cabeçalho e ele. Quando não deixa, ele desce para o fluxo da
// página, no fim do conteúdo (o total e o botão continuam lá, inteiros, ao alcance da
// rolagem: WCAG 1.4.4 e 1.4.10, invariante X11).
//
// Por que 45 %: com a fonte normal, o pior celular em pé é a tela de 568 px de altura com
// a linha de motivo embaixo do botão (cartão de ~120 px), que deixa ~52 %; com a fonte a
// 200 %, a tela mais alta (932 px) deixa no máximo ~43 %. O corte fica entre os dois: a
// fonte normal com o celular em pé nunca muda de comportamento. Deitado, numa tela de
// menos de 768 px de largura (375 px de altura), a fonte normal já deixa ~35 %, e o
// cartão vai para o fluxo também ali: é o mesmo defeito, com a mesma saída.
export const MIN_CONTENT_SHARE = 0.45

export interface ActionDockGeometry {
  /** Altura da tela (`innerHeight`). */
  viewportHeight: number
  /** Altura do que fica preso no alto (o cabeçalho da loja). */
  topChrome: number
  /** Distância do cartão fixo até a base da tela (a navegação e a folga). */
  bottomOffset: number
  /** Altura do próprio cartão. */
  dockHeight: number
}

/** O conteúdo que sobra à vista com o cartão fixo, em fração da tela. */
export function contentShareWithDock (g: ActionDockGeometry): number {
  if (g.viewportHeight <= 0) return 1
  const free = g.viewportHeight - Math.max(0, g.topChrome) - Math.max(0, g.bottomOffset) - Math.max(0, g.dockHeight)
  return Math.max(0, free) / g.viewportHeight
}

/** O cartão pode ficar fixo na base? Falso: ele vai para o fim do conteúdo. */
export function actionDockFits (g: ActionDockGeometry): boolean {
  return contentShareWithDock(g) >= MIN_CONTENT_SHARE
}
