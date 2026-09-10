import { describe, expect, it } from "vitest";

import {
  cpfHint,
  cpfTail,
  digitsOnly,
  enterAction,
  enterActionCaveat,
  enterActionLabel,
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
  const base = { query: "", resultsCount: 0, highlightedIndex: 0, hasCustomerRef: false };

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

  it("0 resultados + texto → cadastro SÓ COM O NOME, que é ato nomeado", () => {
    expect(enterAction({ ...base, query: "Maria Silva" })).toEqual({
      type: "create_name_only", name: "Maria Silva",
    });
    // 11 dígitos com verificador ERRADO não criam cadastro por CPF nem viram
    // telefone às cegas? Viram telefone: 11 dígitos com DDD é o formato BR.
    expect(enterAction({ ...base, query: "52998224724" })).toEqual({
      type: "transfer", field: "phone", value: "52998224724",
    });
  });

  it("query vazia: com CADASTRO associado (ref) conclui; sem nada, não faz nada", () => {
    expect(enterAction({ ...base, hasCustomerRef: true })).toEqual({ type: "conclude" });
    expect(enterAction(base)).toEqual({ type: "none" });
  });

  // ⚠️ A REGRESSÃO DOS DOIS ENTERS. Nome no formulário e nenhum cadastro: o
  // Enter "concluía" e o cliente nascia sem que ninguém tivesse pedido — é
  // assim que aparece o terceiro "João" da semana. Agora a mesma tecla cai no
  // ato NOMEADO que o botão visível oferece.
  it("query vazia + nome no formulário SEM cadastro → não conclui, nomeia o ato", () => {
    expect(enterAction({ ...base, pendingName: "João" })).toEqual({
      type: "create_name_only", name: "João",
    });
  });

  it("o cadastro associado vence o nome pendente: aí concluir é fechar, não criar", () => {
    expect(enterAction({ ...base, hasCustomerRef: true, pendingName: "João" })).toEqual({
      type: "conclude",
    });
  });

  it("nome pendente em branco não inventa cadastro", () => {
    expect(enterAction({ ...base, pendingName: "   " })).toEqual({ type: "none" });
  });
});

describe("enterActionLabel / enterActionCaveat — o botão e a tecla dizem a MESMA coisa", () => {
  it("o rótulo fala do RESULTADO, nunca da tecla", () => {
    expect(enterActionLabel({ type: "create_name_only", name: "Maria Silva" }))
      .toBe("Cadastrar «Maria Silva» só com o nome");
    expect(enterActionLabel({ type: "resolve_cpf", cpf: CPF }))
      .toBe("Cadastrar cliente novo com este CPF");
    expect(enterActionLabel({ type: "transfer", field: "phone", value: "43999990000" }))
      .toBe("Cadastrar cliente novo com o 43999990000");
  });

  it("sem ato para oferecer, não há botão", () => {
    expect(enterActionLabel({ type: "pick", index: 0 })).toBe("");
    expect(enterActionLabel({ type: "conclude" })).toBe("");
    expect(enterActionLabel({ type: "none" })).toBe("");
  });

  it("a ressalva do cadastro só com o nome informa, e só ela existe", () => {
    expect(enterActionCaveat({ type: "create_name_only", name: "Maria" }))
      .toContain("Sem WhatsApp");
    expect(enterActionCaveat({ type: "resolve_cpf", cpf: CPF })).toBe("");
    expect(enterActionCaveat({ type: "none" })).toBe("");
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
