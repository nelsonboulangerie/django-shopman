// Presentation — os desenhos dos pinos do mapa das Entregas (escolha do dono, 21/11:
// "L2, P1 e E4", depois "opção c1!"). Puro: o componente só os põe na tela.
//
//  · A LOJA é o ícone de loja (tabler building-store) em traço, com a parede e o toldo
//    preenchidos de branco por baixo, um pouco maior que a parada.
//  · A PARADA é um cupom (papel com a base em zigue-zague) com o número dentro.
//  · O ENTREGADOR é a própria moto (tabler motorbike), em traço, sem caixa em volta.
//
// Base "c": cada pino e cada linha levam um contorno na cor do TEMA por baixo (branco
// no claro, quase preto no escuro), que os separa do mapa. O papel do cupom e a parede
// da loja são brancos nos dois temas; o desenho e o número, sempre escuros (`GLYPH_INK`).
// A moto não tem papel: o traço dela é o contraste do tema (escuro no claro, branco no
// escuro), como na prévia aprovada.

/** O desenho e o número dentro do papel branco, nos dois temas. */
export const GLYPH_INK = "#111111";
/** O papel do cupom e a parede da loja: brancos sempre. */
export const GLYPH_PAPER = "#ffffff";

/** O contorno na cor do tema, por baixo de pinos e linhas (base "c"). */
export function themeHalo(dark: boolean): string {
  return dark ? GLYPH_INK : GLYPH_PAPER;
}
/** O traço da moto: o contraste do tema. */
export function motoStroke(dark: boolean): string {
  return dark ? GLYPH_PAPER : GLYPH_INK;
}

/** A base do cupom: dentes de `depth` entre `x1` e `x0`, da direita para a esquerda. */
function zigzag(y: number, x0: number, x1: number, teeth: number, depth: number): string {
  const step = (x1 - x0) / (teeth * 2);
  const points: string[] = [];
  for (let k = 0; k <= teeth * 2; k++) {
    points.push(`L${(x1 - step * k).toFixed(1)} ${(k % 2 ? y + depth : y).toFixed(1)}`);
  }
  return points.join(" ");
}
/** O cupom: 30 de largura por 34 de papel, com a base em zigue-zague de 4 dentes. */
export const COUPON_PATH = `M2 2 H32 V36 ${zigzag(36, 2, 32, 4, 4)} Z`;
/** A caixa do cupom (viewBox), com folga para o contorno do tema. */
export const COUPON_VIEWBOX = "-3 -3 40 48";

/** A loja (tabler building-store, MIT), em traço. */
export const STORE_PATH =
  "M3 21h18M3 7v1a3 3 0 0 0 6 0V7m0 1a3 3 0 0 0 6 0V7m0 1a3 3 0 0 0 6 0V7H3l2-4h14l2 4M5 21V10.85M19 21V10.85M9 21v-4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v4";
/** O que é branco por baixo do traço da loja: a parede e o toldo. */
export const STORE_WALL = { x: 4, y: 5, width: 16, height: 16 } as const;
export const STORE_AWNING = "M3 7 L5 3 H19 L21 7 Z";

/** A moto (tabler motorbike, MIT), em traço. */
export const MOTO_PATHS = [
  "M2 16a3 3 0 1 0 6 0a3 3 0 1 0-6 0m14 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0m-8.5-2h5l4-4H6m1.5 4l4-4",
  "M13 6h2l1.5 3l2 4",
] as const;
/** A caixa da loja e da moto (24 de desenho), com folga para o contorno do tema. */
export const ICON_VIEWBOX = "-3 -3 30 30";
