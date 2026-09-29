import { describe, expect, it } from "vitest";

import { deliveryTaxIdMissing, isValidCnpj, isValidCpf, isValidTaxId, maskTaxId, taxIdEcho } from "~/presentation/taxId";

describe("taxId — o dígito verificador, do lado da tela", () => {
  it("aceita CPF real, pontuado ou cru", () => {
    expect(isValidCpf("52998224725")).toBe(true);
    expect(isValidCpf("529.982.247-25")).toBe(true);
  });

  it("recusa CPF com dígito errado", () => {
    expect(isValidCpf("52998224726")).toBe(false);
  });

  it("recusa a sequência repetida — a que mais aparece quando se digita sem olhar", () => {
    // Ela FECHA na aritmética do módulo 11; sem o caso especial, passaria.
    expect(isValidCpf("11111111111")).toBe(false);
    expect(isValidCpf("00000000000")).toBe(false);
    expect(isValidCnpj("11111111111111")).toBe(false);
  });

  it("recusa contagem de dígitos que não é documento", () => {
    expect(isValidCpf("5299822472")).toBe(false);
    expect(isValidTaxId("")).toBe(false);
    expect(isValidTaxId("529982247251")).toBe(false);
  });

  it("aceita CNPJ real e recusa o adulterado", () => {
    expect(isValidCnpj("11222333000181")).toBe(true);
    expect(isValidCnpj("11.222.333/0001-81")).toBe(true);
    expect(isValidCnpj("11222333000182")).toBe(false);
  });

  it("isValidTaxId roteia pelos onze ou catorze dígitos", () => {
    expect(isValidTaxId("529.982.247-25")).toBe(true);
    expect(isValidTaxId("11.222.333/0001-81")).toBe(true);
  });
});

describe("entrega com nota exige o documento", () => {
  const base = { fulfillmentType: "delivery", required: true, wantsCpfOnInvoice: true, invoiceTaxId: "529.982.247-25" };

  it("trava sem CPF, com CPF errado ou com o toggle desligado", () => {
    expect(deliveryTaxIdMissing({ ...base, invoiceTaxId: "" })).toBe(true);
    expect(deliveryTaxIdMissing({ ...base, invoiceTaxId: "529.982.247-00" })).toBe(true);
    expect(deliveryTaxIdMissing({ ...base, wantsCpfOnInvoice: false })).toBe(true);
  });

  it("libera com o documento certo", () => {
    expect(deliveryTaxIdMissing(base)).toBe(false);
  });

  it("não se mete na retirada nem na entrega sem nota", () => {
    expect(deliveryTaxIdMissing({ ...base, fulfillmentType: "pickup", invoiceTaxId: "" })).toBe(false);
    expect(deliveryTaxIdMissing({ ...base, required: false, invoiceTaxId: "" })).toBe(false);
    expect(deliveryTaxIdMissing({ ...base, required: undefined, invoiceTaxId: "" })).toBe(false);
  });
});

// A máscara e o eco moram aqui para a venda (checkout) e a edição da encomenda
// (caixa de "Salvar alterações") conferirem o documento do MESMO jeito.
describe("taxId — máscara e eco, os mesmos na venda e na edição", () => {
  it("mascara CPF e CNPJ e corta no 14º dígito", () => {
    expect(maskTaxId("52998224725")).toBe("529.982.247-25");
    expect(maskTaxId("11222333000181")).toBe("11.222.333/0001-81");
    expect(maskTaxId("112223330001819")).toBe("11.222.333/0001-81");
  });

  it("o eco confere o dígito, não só a contagem", () => {
    expect(taxIdEcho("")).toEqual({ ok: false, text: "Digite o documento. Sem ele, a nota sai sem CPF." });
    expect(taxIdEcho("5299822")).toEqual({ ok: false, text: "Documento incompleto: a nota sai sem CPF." });
    expect(taxIdEcho("52998224726")).toEqual({ ok: false, text: "Documento inválido. Confira com o cliente." });
    expect(taxIdEcho("52998224725")).toEqual({ ok: true, text: "Sai na nota: CPF 529.982.247-25" });
    expect(taxIdEcho("11222333000181")).toEqual({ ok: true, text: "Sai na nota: CNPJ 11.222.333/0001-81" });
  });
});
