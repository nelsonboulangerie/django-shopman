// Presentation — os desenhos dos pinos do mapa das Entregas. Puro: o componente só os
// põe na tela. Decisões do dono (21/11): loja L2, moto E4 e a parada como PACOTE (o saco
// de pão: picote em cima, base reta embaixo), "V2, sem fio".
//
//  · O TRAÇO de todo ícone tem a mesma espessura da linha da rota (`ROUTE_WIDTH`), sem
//    escalar com o ícone (`vector-effect: non-scaling-stroke`).
//  · A MOTO e o PACOTE são inteiros na cor da rota; o pacote é cheio dela, com o código do
//    pedido no corpo, na cor de texto que lê sobre ela (4,5:1). A LOJA fica neutra: traço
//    escuro sobre parede e toldo brancos.
//  · A corrida preta vira quase branca no escuro (a rota preta sumiria no papel escuro).
//  · Por baixo de tudo, um contorno na cor do TEMA (branco no claro, quase preto no
//    escuro), que separa o desenho do mapa. Nada tem transparência.
//  · O pacote marca o lugar pelo CENTRO DA BASE: a base reta pousa no ponto do mapa.
import { contrast } from "./deliveriesMap";

/** A espessura da linha da rota, e do traço de todo ícone do mapa (px). */
export const ROUTE_WIDTH = 4;
/** O contorno do tema por baixo de linhas e ícones: 2 px de cada lado. */
export const HALO_WIDTH = ROUTE_WIDTH + 4;
/** O traço escuro da loja e o texto escuro. */
export const GLYPH_INK = "#111111";
/** A parede da loja e o papel do pacote em edição: brancos sempre. */
export const GLYPH_PAPER = "#ffffff";
/** A corrida preta no escuro. */
export const DARK_BLACK_ROUTE = "#f1ece4";

/** O contorno na cor do tema, por baixo de pinos e linhas. */
export function themeHalo(dark: boolean): string {
  return dark ? GLYPH_INK : GLYPH_PAPER;
}

/** A cor da rota de uma corrida: a da amostra; a preta, quase branca no escuro. */
export function routeColor(dark: boolean, ride: { bg: string }): string {
  return dark && ride.bg.toLowerCase() === GLYPH_INK ? DARK_BLACK_ROUTE : ride.bg;
}

/** O texto sobre o pacote cheio: o branco ou o escuro, o que ler mais sobre a cor. */
export function textOn(fill: string): string {
  return contrast(GLYPH_PAPER, fill) >= contrast(GLYPH_INK, fill) ? GLYPH_PAPER : GLYPH_INK;
}

/** O picote do topo: dentes de `depth` entre `x0` e `x1`, da direita para a esquerda. */
function perforation(y: number, x0: number, x1: number, teeth: number, depth: number): string {
  const step = (x1 - x0) / (teeth * 2);
  const points: string[] = [];
  for (let k = 0; k <= teeth * 2; k++) {
    points.push(`L${(x1 - step * k).toFixed(2)} ${(k % 2 ? y - depth : y).toFixed(1)}`);
  }
  return points.join(" ");
}
/** O pacote: 30 de largura, base reta em y=40, picote de 4 dentes no topo (y 2 a 6). */
export const PACKAGE_PATH = `M2 40 H32 V6 ${perforation(6, 2, 32, 4, 4)} Z`;
export const PACKAGE_VIEWBOX = "0 0 34 42";
/** Onde o código fica: o meio do corpo, abaixo do picote. */
export const PACKAGE_TEXT_Y = 24;

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
/** A caixa da loja e da moto (24 de desenho). */
export const ICON_VIEWBOX = "0 0 24 24";
