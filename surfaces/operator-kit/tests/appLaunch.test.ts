import { describe, expect, it } from "vitest";
import {
  crossAppLinkAttrs,
  EXTERNAL_LINK_ATTRS,
  houseHref,
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

// Coordenação, 21/11/2026: link para FORA da casa abre em nova aba, sempre. O operador
// não perde o Gestor para ir ao Portal. Entre apps da casa, a regra de sempre.
describe("houseHref: app da casa × site de fora", () => {
  const GESTOR = "https://gestor.boulangerie.com.br";

  it("o irmão sob o mesmo domínio e a API são da casa", () => {
    expect(houseHref("https://pdv.boulangerie.com.br/", GESTOR)).toBe(true);
    expect(houseHref("https://api.boulangerie.com.br/admin/", GESTOR)).toBe(true);
    expect(houseHref("https://boulangerie.com.br/", GESTOR)).toBe(true);
    expect(houseHref(CENTRAL, PDV)).toBe(true); // o local, `.boulangerie`
  });

  it("em dev, outra porta no mesmo host é da casa", () => {
    expect(houseHref("http://127.0.0.1:3002/", "http://127.0.0.1:3004")).toBe(true);
    expect(houseHref("http://192.168.0.9:3002/", "http://127.0.0.1:3004")).toBe(false);
    // `localhost` e `127.0.0.1` são esta máquina: o mesmo lugar.
    expect(houseHref("http://127.0.0.1:3005/", "http://localhost:3000")).toBe(true);
  });

  it("Portal do iFood, ManyChat, Google, WhatsApp e a loja do cliente são de fora", () => {
    for (const href of [
      "https://portal.ifood.com.br/",
      "https://app.manychat.com/fb123/chat/9",
      "https://merchants.google.com/",
      "https://wa.me/5543999990000",
      "https://www.nelsonboulangerie.com.br/pedido/A17",
    ])
      expect(houseHref(href, GESTOR)).toBe(false);
  });

  it("sufixo público nunca vira domínio da casa", () => {
    expect(houseHref("https://outra-loja.com.br/", "https://boulangerie.com.br")).toBe(false);
    expect(houseHref("https://qualquer.com/", "https://loja.com")).toBe(false);
  });

  it("relativo e inválido não viram navegação para fora", () => {
    expect(houseHref("/pedidos", GESTOR)).toBe(true);
    expect(houseHref("::não é url::", GESTOR)).toBe(true);
  });
});

describe("crossAppLinkAttrs: site de fora", () => {
  it("abre em nova aba instalado ou não, com noopener", () => {
    for (const installed of [true, false]) {
      expect(
        crossAppLinkAttrs({ installed, href: "https://portal.ifood.com.br/", currentOrigin: "https://gestor.boulangerie.com.br" }),
      ).toEqual({ target: "_blank", rel: "noopener" });
    }
  });

  it("o app irmão segue a regra de sempre: na aba, a mesma; instalado, a janela dele", () => {
    const href = "https://pdv.boulangerie.com.br/";
    const currentOrigin = "https://gestor.boulangerie.com.br";
    expect(crossAppLinkAttrs({ installed: false, href, currentOrigin })).toEqual({ target: "_self" });
    expect(crossAppLinkAttrs({ installed: true, href, currentOrigin })).toEqual({ target: "_blank", rel: "noopener" });
  });
});
