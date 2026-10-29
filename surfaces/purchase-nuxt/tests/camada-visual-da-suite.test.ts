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

describe("Compras no shell da suíte (fase 2)", () => {
  it("o app entrega as seções ao shell do kit, sem navegação própria nem a pele legada", () => {
    const shell = app("app.vue");
    expect(shell).toContain("<OperatorSuiteShell");
    expect(shell).toContain(':sections="sections"');
    expect(shell).not.toMatch(/data-suite=/);
    expect(shell).not.toContain("<PurchaseNav");
    expect(shell).not.toContain("<OperatorSuiteRail");
    expect(shell).not.toContain("<nav");
  });

  it("cada seção é uma rota; a Base separa cadastros das tarefas, sempre em rota inglesa", () => {
    for (const page of ["pages/index.vue", "pages/buy.vue", "pages/receive.vue", "pages/base/materials.vue", "pages/base/suppliers.vue", "pages/base/costs.vue", "pages/base/count.vue"]) {
      const source = app(page);
      expect(source, page).toContain("<OperatorPageHeader");
      expect(source, page).toContain("<PurchaseReadStatus");
    }
    expect(app("pages/base/index.vue")).toContain('redirect: "/base/materials"');
  });
});

describe("CRUD humano da Base", () => {
  it("o detalhe móvel é página, não gaveta, e a lista sai do caminho", () => {
    const materials = app("pages/base/materials.vue");
    const material = app("pages/base/materials/[sku].vue");
    const suppliers = app("pages/base/suppliers.vue");
    const supplier = app("pages/base/suppliers/[ref].vue");

    expect(materials).toContain("max-xl:hidden");
    expect(suppliers).toContain("max-xl:hidden");
    expect(material).toContain("data-material-page");
    expect(supplier).toContain("data-supplier-page");
    expect(material).not.toContain("<NuxtSlideover");
    expect(supplier).not.toContain("<NuxtSlideover");
  });

  it("a leitura usa a barra inferior; a edição mantém a barra Salvar/Descartar do casco", () => {
    for (const detail of ["pages/base/materials/[sku].vue", "pages/base/suppliers/[ref].vue"]) {
      const source = app(detail);
      expect(source, detail).toContain("<OperatorActionBar");
      expect(source, detail).toContain(':secondary="previousAction"');
      expect(source, detail).toContain(':action="nextAction"');
    }
    const shell = readFileSync(resolve(__dirname, "../../operator-kit/app/components/OperatorFormShell.vue"), "utf8");
    expect(shell).toContain("<OperatorActionBar");
    expect(shell).toContain(':secondary="discardAction()"');
  });

  it("formulários usam página neutra, cards claros e não alternam blocos elevados", () => {
    for (const form of ["components/PurchaseMaterialFormPanel.vue", "components/PurchaseSupplierFormPanel.vue"]) {
      const source = app(form);
      expect(source, form).toContain("data-crud-form-surface");
      expect(source, form).toContain("bg-background");
      expect(source, form).toContain("rounded-md border bg-card p-4");
      expect(source, form).not.toContain("bg-elevated/60");
    }
  });

  it("custos e contagem têm nome de tarefa e volta explícita aos insumos", () => {
    const costs = app("pages/base/costs.vue");
    const count = app("pages/base/count.vue");
    expect(costs).toContain('title="Lançar custos"');
    expect(count).toContain('title="Contar estoque"');
    expect(costs).toContain('label="Voltar aos insumos"');
    expect(count).toContain('label="Voltar aos insumos"');
  });
});
