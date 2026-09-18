import { describe, expect, it } from "vitest";

import {
  VIEWPORT_NOISE_PX,
  viewportState,
} from "../app/utils/visualViewport";

// ⚠️ O defeito que isto existe para impedir, medido num iPhone: ao tocar no campo
// "Motivo" da recusa, o teclado subia e a CAIXA SUMIA atrás dele — não dava nem para
// ver o que se estava escrevendo. Não era defeito daquela tela: toda caixa do sistema é
// `position: fixed` centrada em `top: 50%`, e no iOS o teclado não encolhe o viewport de
// layout, só o visual. O navegador seguia centrando a caixa no meio de uma janela cuja
// metade de baixo estava debaixo do teclado.
describe("o espaço que sobra quando o teclado sobe", () => {
  // ⚠️ `covered: false` é o que deixa o CSS DESLIGADO. Não basta as variáveis voltarem
  // ao valor neutro: `top: 50%` e `50dvh` não são a mesma coisa em todo navegador de
  // celular, e nove superfícies montam esta folha. Com o teclado fechado nenhuma regra
  // nova pode entrar em vigor.
  it("com o teclado fechado, nenhuma regra nova entra em vigor", () => {
    const state = viewportState({
      layoutHeight: 844,
      visualHeight: 844,
      offsetTop: 0,
    });

    expect(state.covered).toBe(false);
    expect(state.variables).toEqual({
      "--viewport-visible-height": "100dvh",
      "--viewport-visible-top": "0px",
      "--viewport-bottom-inset": "0px",
    });
  });

  it("com o teclado aberto, a caixa se centra no que sobrou", () => {
    // iPhone de 844pt com o teclado do iOS ocupando 336pt.
    expect(
      viewportState({
        layoutHeight: 844,
        visualHeight: 508,
        offsetTop: 0,
      }),
    ).toEqual({
      covered: true,
      variables: {
        "--viewport-visible-height": "508px",
        "--viewport-visible-top": "0px",
        "--viewport-bottom-inset": "336px",
      },
    });
  });

  it("conta o deslocamento do topo, que o iOS soma quando rola o viewport visual", () => {
    expect(
      viewportState({
        layoutHeight: 844,
        visualHeight: 508,
        offsetTop: 100,
      }).variables,
    ).toEqual({
      "--viewport-visible-height": "508px",
      "--viewport-visible-top": "100px",
      "--viewport-bottom-inset": "236px",
    });
  });

  // ⚠️ A barra de endereço do Safari muda a altura visual em um ou dois pixels durante
  // a rolagem. Sem a folga, a caixa TREMERIA a cada rolagem — um defeito pior do que o
  // que estamos consertando.
  it("ignora o ruído da barra de endereço em vez de tremer a caixa", () => {
    expect(
      viewportState({
        layoutHeight: 844,
        visualHeight: 844 - VIEWPORT_NOISE_PX,
        offsetTop: 0,
      }).covered,
    ).toBe(false);

    expect(
      viewportState({
        layoutHeight: 844,
        visualHeight: 844 - VIEWPORT_NOISE_PX - 1,
        offsetTop: 0,
      }).covered,
    ).toBe(true);
  });

  // Degradação, nunca erro: navegador sem `visualViewport` ou medida impossível
  // devolve o CSS de sempre.
  it("sem medida utilizável, devolve o que o CSS já fazia", () => {
    for (const geometry of [
      { layoutHeight: 0, visualHeight: 0, offsetTop: 0 },
      { layoutHeight: 844, visualHeight: 0, offsetTop: 0 },
      { layoutHeight: Number.NaN, visualHeight: 508, offsetTop: 0 },
    ]) {
      expect(viewportState(geometry).covered).toBe(false);
    }
  });

  it("nunca devolve número negativo, mesmo com medida incoerente", () => {
    const state = viewportState({
      layoutHeight: 400,
      visualHeight: 900,
      offsetTop: 0,
    });

    expect(state.variables["--viewport-bottom-inset"]).toBe("0px");
    expect(state.covered).toBe(false);
  });
});
