import { describe, expect, it } from "vitest";

import { isValidCnpj, isValidCpf, isValidTaxId } from "~/presentation/taxId";

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
