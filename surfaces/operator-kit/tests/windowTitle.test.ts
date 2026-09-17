import { describe, expect, it } from "vitest";
import { operatorAppName, windowTitle } from "../app/presentation/windowTitle";

const pdv = operatorAppName("Nelson", "PDV");

describe("operatorAppName", () => {
  it("junta a casa e o rótulo com ponto médio", () => {
    expect(pdv).toEqual({ prefix: "Nelson", label: "PDV", name: "Nelson · PDV" });
    expect(operatorAppName(" Nelson ", " B.I. ").name).toBe("Nelson · B.I.");
  });

  it("sem casa o nome é só o rótulo", () => {
    expect(operatorAppName("", "KDS").name).toBe("KDS");
    expect(operatorAppName(null, "KDS").name).toBe("KDS");
  });

  it("troca separador de hífen ou barra pelo ponto médio", () => {
    expect(operatorAppName("Casa - Centro", "PDV").name).toBe("Casa · Centro · PDV");
  });
});

describe("windowTitle", () => {
  it("põe o nome do app na frente para o Chrome não prefixar o nome do PWA", () => {
    expect(windowTitle(pdv, "Filipetas")).toBe("Nelson · PDV · Filipetas");
    expect(windowTitle(operatorAppName("Nelson", "Gestor"), "Canais")).toBe("Nelson · Gestor · Canais");
  });

  it("sem título de página mostra só o nome do app", () => {
    expect(windowTitle(pdv)).toBe("Nelson · PDV");
    expect(windowTitle(pdv, undefined)).toBe("Nelson · PDV");
    expect(windowTitle(pdv, null)).toBe("Nelson · PDV");
    expect(windowTitle(pdv, "")).toBe("Nelson · PDV");
    expect(windowTitle(pdv, "   ")).toBe("Nelson · PDV");
  });

  it("não duplica quando a página é o próprio app (rótulo ou nome inteiro)", () => {
    expect(windowTitle(pdv, "PDV")).toBe("Nelson · PDV");
    expect(windowTitle(pdv, "Nelson · PDV")).toBe("Nelson · PDV");
    expect(windowTitle(operatorAppName("Nelson", "Produção"), " Produção ")).toBe("Nelson · Produção");
  });

  it("aceita o rótulo cru como string (app sem casa)", () => {
    expect(windowTitle("PDV", "Filipetas")).toBe("PDV · Filipetas");
  });

  it("sem nome de app devolve o título da página intacto", () => {
    expect(windowTitle("", "Filipetas")).toBe("Filipetas");
    expect(windowTitle("", "")).toBe("");
  });

  it("a página de erro padrão do Nuxt não traz hífen para a barra da janela", () => {
    const title = windowTitle(pdv, "404 - Page not found | Nuxt");
    expect(title).toBe("Nelson · PDV · 404 · Page not found · Nuxt");
    expect(title).not.toMatch(/\s[-–—|]\s/);
  });

  it("hífen dentro de palavra não é separador", () => {
    expect(windowTitle(pdv, "Pão-de-queijo")).toBe("Nelson · PDV · Pão-de-queijo");
  });
});
