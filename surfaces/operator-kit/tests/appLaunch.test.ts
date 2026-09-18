import { describe, expect, it } from "vitest";
import {
  crossAppLinkAttrs,
  EXTERNAL_LINK_ATTRS,
  sameOrigin,
} from "../app/presentation/appLaunch";

const PDV = "https://pdv.boulangerie";
const CENTRAL = "https://central.boulangerie/";

describe("sameOrigin", () => {
  it("relativo é sempre a própria origem", () => {
    expect(sameOrigin("/session", PDV)).toBe(true);
    expect(sameOrigin("/display", PDV)).toBe(true);
  });

  it("o subdomínio irmão é OUTRA origem — é disso que nasce a tarja", () => {
    expect(sameOrigin(CENTRAL, PDV)).toBe(false);
    expect(sameOrigin("https://cozinha.boulangerie/", PDV)).toBe(false);
  });

  it("a mesma origem escrita por extenso continua a mesma", () => {
    expect(sameOrigin("https://pdv.boulangerie/session", PDV)).toBe(true);
  });

  it("href quebrado não vira navegação para fora", () => {
    expect(sameOrigin("::não é url::", PDV)).toBe(true);
  });
});

describe("crossAppLinkAttrs", () => {
  it("INSTALADO: o outro app abre na janela dele, e o `noopener` é o que permite isso", () => {
    // Capturável = cria frame novo e não é contexto auxiliar. `_blank` sem `noopener`
    // guarda `opener`, é auxiliar, e o Chrome NÃO captura — abriria uma janela solta
    // do navegador em vez do app.
    expect(crossAppLinkAttrs({ installed: true, href: CENTRAL, currentOrigin: PDV }))
      .toEqual({ target: "_blank", rel: "noopener" });
  });

  it("NAVEGADOR: segue na mesma aba — `_blank` ali só empilharia aba a cada troca", () => {
    expect(crossAppLinkAttrs({ installed: false, href: CENTRAL, currentOrigin: PDV }))
      .toEqual({ target: "_self" });
  });

  it("mesma origem nunca sai da janela, instalado ou não", () => {
    for (const installed of [true, false]) {
      expect(crossAppLinkAttrs({ installed, href: "/session", currentOrigin: PDV }))
        .toEqual({ target: "_self" });
    }
  });

  it("href vazio não vira link para lugar nenhum", () => {
    expect(crossAppLinkAttrs({ installed: true, href: "", currentOrigin: PDV }))
      .toEqual({ target: "_self" });
  });

  it("link para fora da casa abre em outra janela sempre", () => {
    expect(EXTERNAL_LINK_ATTRS).toEqual({ target: "_blank", rel: "noopener" });
  });
});
