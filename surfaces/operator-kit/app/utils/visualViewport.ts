// O teclado virtual do celular e a caixa que ele cobre.
//
// ⚠️ O problema, medido num iPhone: ao tocar no campo "Motivo" da recusa, o teclado
// sobe e a caixa some atrás dele — não dá nem para ver o que se está escrevendo. Não é
// defeito daquela tela: TODA caixa do sistema é `position: fixed` centrada em
// `top: 50%`, e no iOS o teclado NÃO encolhe o viewport de layout. Ele encolhe só o
// viewport VISUAL. Então o navegador continua centrando a caixa no meio de uma janela
// cuja metade de baixo está debaixo do teclado.
//
// `interactive-widget=resizes-content` no meta viewport resolveria de forma
// declarativa, mas é do Chrome/Android; o iOS ignora. O que o iOS dá é a
// `window.visualViewport`, e é dela que estes números saem.
//
// Esta função é PURA de propósito: ela só faz a conta. Quem escuta o navegador e
// escreve no `:root` é o plugin ao lado, e é isso que deixa a conta testável sem um
// telefone na mão.

export interface ViewportGeometry {
  /** Altura da janela de layout — a que o CSS chama de `100vh`. */
  layoutHeight: number;
  /** Altura do que a pessoa REALMENTE vê agora. Encolhe quando o teclado sobe. */
  visualHeight: number;
  /** Quanto o viewport visual desceu dentro do de layout (rolagem por zoom/teclado). */
  offsetTop: number;
}

export interface ViewportVariables {
  /** Altura útil: o espaço que sobra entre o topo visível e o teclado. */
  "--viewport-visible-height": string;
  /** Onde começa o espaço útil, medido do topo da janela de layout. */
  "--viewport-visible-top": string;
  /** Quanto está coberto na base. Zero com o teclado fechado. */
  "--viewport-bottom-inset": string;
}

/** Tolerância em pixels antes de chamar uma diferença de "teclado".
 *
 * ⚠️ A barra de endereço do Safari muda a altura visual em um ou dois pixels durante a
 * rolagem, e arredondamento de zoom faz o mesmo. Sem esta folga, a caixa tremeria a
 * cada rolagem — um defeito pior do que o que estamos consertando. */
export const VIEWPORT_NOISE_PX = 24;

export function viewportVariables(
  geometry: ViewportGeometry,
): ViewportVariables {
  const layout = Math.max(0, Math.round(geometry.layoutHeight || 0));
  const visual = Math.max(0, Math.round(geometry.visualHeight || 0));
  const offset = Math.max(0, Math.round(geometry.offsetTop || 0));
  // Sem dado utilizável, devolve a janela inteira: o CSS volta a ser o de sempre.
  if (!layout || !visual) {
    return {
      "--viewport-visible-height": "100dvh",
      "--viewport-visible-top": "0px",
      "--viewport-bottom-inset": "0px",
    };
  }
  const covered = Math.max(0, layout - visual - offset);
  // Diferença pequena é ruído da barra de endereço, não teclado.
  const settled = covered <= VIEWPORT_NOISE_PX && offset <= VIEWPORT_NOISE_PX;
  if (settled) {
    return {
      "--viewport-visible-height": "100dvh",
      "--viewport-visible-top": "0px",
      "--viewport-bottom-inset": "0px",
    };
  }
  return {
    "--viewport-visible-height": `${visual}px`,
    "--viewport-visible-top": `${offset}px`,
    "--viewport-bottom-inset": `${covered}px`,
  };
}
