import { describe, expect, it } from "vitest";

import {
  cpfHint,
  cpfTail,
  digitsOnly,
  enterAction,
  formatCpf,
  isNumericQuery,
  isValidCpf,
  maskQueryIfCpf,
  moveHighlight,
} from "~/presentation/customerSearch";

// CPF de exemplo clássico, com verificadores corretos.
const CPF = "52998224725";

describe("digitsOnly / isNumericQuery", () => {
  it("arranca tudo que não é dígito", () => {
    expect(digitsOnly("529.982.247-25")).toBe(CPF);
    expect(digitsOnly("(43) 99999-0000")).toBe("43999990000");
    expect(digitsOnly("Maria")).toBe("");
  });

  it("query numérica = dígitos e pontuação de máscara, nada de letra", () => {
    expect(isNumericQuery("529.982.247-25")).toBe(true);
    expect(isNumericQuery("(43) 99999-0000")).toBe(true);
    expect(isNumericQuery("Maria")).toBe(false);
    expect(isNumericQuery("Rua 15")).toBe(false);
    expect(isNumericQuery("")).toBe(false);
    expect(isNumericQuery("--")).toBe(false); // pontuação sem dígito não conta
  });
});

describe("isValidCpf — dígitos verificadores de verdade", () => {
  it("aceita CPF válido, cru ou mascarado", () => {
    expect(isValidCpf(CPF)).toBe(true);
    expect(isValidCpf("529.982.247-25")).toBe(true);
  });

  it("recusa verificador errado", () => {
    expect(isValidCpf("52998224724")).toBe(false);
    expect(isValidCpf("52998224735")).toBe(false);
  });

  it("recusa comprimento errado e sequência repetida", () => {
    expect(isValidCpf("5299822472")).toBe(false);
    expect(isValidCpf("529982247251")).toBe(false);
    expect(isValidCpf("11111111111")).toBe(false);
    expect(isValidCpf("00000000000")).toBe(false);
  });
});

describe("formatCpf / maskQueryIfCpf / cpfHint / cpfTail", () => {
  it("mascara 11 dígitos como 000.000.000-00", () => {
    expect(formatCpf(CPF)).toBe("529.982.247-25");
    expect(formatCpf("1234")).toBe("1234"); // parcial fica cru
  });

  it("o eco do input só mascara CPF VÁLIDO; telefone e parcial ficam crus", () => {
    expect(maskQueryIfCpf(CPF)).toBe("529.982.247-25");
    expect(maskQueryIfCpf("529.982.247-25")).toBe("529.982.247-25"); // idempotente
    expect(maskQueryIfCpf("52998224724")).toBe("52998224724"); // inválido: cru
    expect(maskQueryIfCpf("4399999")).toBe("4399999");
    expect(maskQueryIfCpf("Maria")).toBe("Maria");
  });

  it("o aviso só fala com 11 dígitos numéricos", () => {
    expect(cpfHint(CPF)).toBe("valid");
    expect(cpfHint("52998224724")).toBe("invalid");
    expect(cpfHint("529982247")).toBe("");
    expect(cpfHint("Maria")).toBe("");
  });

  it("o rabo confirma sem expor o documento inteiro", () => {
    expect(cpfTail(CPF)).toBe("···247-25");
    expect(cpfTail("529.982.247-25")).toBe("···247-25");
    expect(cpfTail("1234")).toBe("");
  });
});

describe("enterAction — a decisão do Enter, em ordem de intenção", () => {
  const base = { query: "", resultsCount: 0, highlightedIndex: 0, hasCustomer: false };

  it("1 resultado → seleciona, seja qual for a query", () => {
    expect(enterAction({ ...base, query: "Mar", resultsCount: 1 })).toEqual({ type: "pick", index: 0 });
  });

  it("N resultados → seleciona o destacado (índice fora do alcance é grampeado)", () => {
    expect(enterAction({ ...base, query: "Ma", resultsCount: 3, highlightedIndex: 2 })).toEqual({ type: "pick", index: 2 });
    expect(enterAction({ ...base, query: "Ma", resultsCount: 3, highlightedIndex: 9 })).toEqual({ type: "pick", index: 2 });
    expect(enterAction({ ...base, query: "Ma", resultsCount: 3, highlightedIndex: -1 })).toEqual({ type: "pick", index: 0 });
  });

  it("0 resultados + CPF válido → resolve direto pelo documento", () => {
    expect(enterAction({ ...base, query: "529.982.247-25" })).toEqual({ type: "resolve_cpf", cpf: CPF });
  });

  it("0 resultados + 10-11 dígitos não-CPF → transfere para o telefone", () => {
    expect(enterAction({ ...base, query: "(43) 99999-0000" })).toEqual({
      type: "transfer", field: "phone", value: "43999990000",
    });
    expect(enterAction({ ...base, query: "4399990000" })).toEqual({
      type: "transfer", field: "phone", value: "4399990000",
    });
  });

  it("0 resultados + texto → transfere para o nome", () => {
    expect(enterAction({ ...base, query: "Maria Silva" })).toEqual({
      type: "transfer", field: "name", value: "Maria Silva",
    });
    // 11 dígitos com verificador ERRADO não criam cadastro por CPF nem viram
    // telefone às cegas? Viram telefone: 11 dígitos com DDD é o formato BR.
    expect(enterAction({ ...base, query: "52998224724" })).toEqual({
      type: "transfer", field: "phone", value: "52998224724",
    });
  });

  it("query vazia: com cliente associado conclui; sem, não faz nada", () => {
    expect(enterAction({ ...base, hasCustomer: true })).toEqual({ type: "conclude" });
    expect(enterAction(base)).toEqual({ type: "none" });
  });
});

describe("moveHighlight — combobox com volta pelas pontas", () => {
  it("navega e dá a volta", () => {
    expect(moveHighlight(0, 1, 3)).toBe(1);
    expect(moveHighlight(2, 1, 3)).toBe(0);
    expect(moveHighlight(0, -1, 3)).toBe(2);
  });

  it("sem resultados não há destaque", () => {
    expect(moveHighlight(0, 1, 0)).toBe(-1);
  });

  it("sem destaque anterior, ↓ vai ao primeiro e ↑ ao último", () => {
    expect(moveHighlight(-1, 1, 3)).toBe(0);
    expect(moveHighlight(-1, -1, 3)).toBe(2);
  });
});
