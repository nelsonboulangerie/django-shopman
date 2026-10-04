// V4-COMPRAS: o Compras veste a camada visual da suíte (modelo do Gestor, #1448/#1451).
// Contrato, não estilo:
//
// 1. o shell liga a camada (`data-suite="v3"`) e as seções moram no rail da suíte e na
//    barra do polegar, as duas peças do kit, sem barra de seções própria;
// 2. cada vista abre com o cabeçalho de uma linha do kit;
// 3. o documento da entrada no cabeçalho sai da própria chave da NF, sem inventar número.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { invoiceKeyTail, invoiceNumberLabel } from "../app/presentation/purchase";

const app = (path: string) => readFileSync(resolve(__dirname, "../app", path), "utf8");

// Chave de 44 dígitos: UF 35, AAMM 2610, CNPJ, modelo 55, série 001, número 000012884,
// tipo 1, código 00004170, DV 3.
const KEY = "35261012345678000190550010000128841000041703";

describe("documento da entrada no cabeçalho", () => {
  it("lê o número da NF das posições 26 a 34 da chave", () => {
    expect(KEY).toHaveLength(44);
    expect(invoiceNumberLabel(KEY)).toBe("NF 12.884");
  });

  it("chave ausente ou incompleta não vira número inventado", () => {
    expect(invoiceNumberLabel("")).toBe("");
    expect(invoiceNumberLabel(null)).toBe("");
    expect(invoiceNumberLabel("3526101234")).toBe("");
  });

  it("o selo da chave mostra só o fim, para conferir com o DANFE", () => {
    expect(invoiceKeyTail(KEY)).toBe("Chave …1703");
    expect(invoiceKeyTail("")).toBe("");
  });
});

describe("camada visual da suíte no Compras", () => {
  it("o shell liga a camada e monta a navegação da suíte nos dois lugares", () => {
    const shell = app("app.vue");
    expect(shell).toContain('data-suite="v3"');
    expect(shell).toContain('<PurchaseNav\n      v-if="canIdentify"\n      place="rail"');
    expect(shell).toContain('place="bar"');
    expect(shell).not.toContain("<OperatorRail");
    expect(shell).not.toContain("<nav");
  });

  it("as seções são estado: as peças recebem a vista e devolvem a escolha", () => {
    const nav = app("components/PurchaseNav.vue");
    expect(nav).toContain("<OperatorSuiteRail");
    expect(nav).toContain("<OperatorSectionBar");
    expect(nav).toContain(':current="view"');
    expect(nav).toContain('@select="select"');
    for (const key of ['"panel"', '"buy"', '"receive"', '"base"']) expect(nav).toContain(`key: ${key}`);
  });

  it("toda vista abre com o cabeçalho de uma linha do kit", () => {
    const page = app("pages/index.vue");
    expect(page).toContain("<OperatorPageHeader");
    expect(page).toContain("<OperatorLiveStatus");
    expect(page).toContain('panel: "Painel", buy: "Comprar", receive: "Receber", base: "Base"');
  });
});
