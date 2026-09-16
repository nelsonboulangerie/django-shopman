import { describe, expect, it } from "vitest";
import { windowTitle } from "../app/presentation/windowTitle";

describe("windowTitle", () => {
  it("põe o app na frente para o Chrome não prefixar o nome do PWA", () => {
    expect(windowTitle("PDV", "Filipetas")).toBe("PDV · Filipetas");
    expect(windowTitle("Gestor de Pedidos", "Canais")).toBe("Gestor de Pedidos · Canais");
  });

  it("sem título de página mostra só o nome do app", () => {
    expect(windowTitle("PDV")).toBe("PDV");
    expect(windowTitle("PDV", undefined)).toBe("PDV");
    expect(windowTitle("PDV", null)).toBe("PDV");
    expect(windowTitle("PDV", "")).toBe("PDV");
    expect(windowTitle("PDV", "   ")).toBe("PDV");
  });

  it("não duplica quando a página já é o próprio app", () => {
    expect(windowTitle("PDV", "PDV")).toBe("PDV");
    expect(windowTitle("Produção", " Produção ")).toBe("Produção");
  });

  it("sem nome de app devolve o título da página intacto", () => {
    expect(windowTitle("", "Filipetas")).toBe("Filipetas");
    expect(windowTitle("", "")).toBe("");
  });

  it("apara espaços das duas pontas", () => {
    expect(windowTitle(" PDV ", " Sessão de caixa ")).toBe("PDV · Sessão de caixa");
  });
});
