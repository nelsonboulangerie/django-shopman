import { describe, expect, it } from "vitest";
import {
  buildRowPatches,
  pasteBlock,
  rowProblems,
  sheetKey,
} from "../app/presentation/productSheet";
import type { ProductSheetRow } from "../app/types/catalog";

const profiles = [
  { key: "revenda_st", name: "Revenda com ST", requires_cest: true },
  { key: "producao_propria", name: "Produção própria", requires_cest: false },
];
const origins = [
  { key: "0", name: "Nacional" },
  { key: "1", name: "Estrangeira" },
];
const choices = { profiles, origins };

const row = (sku: string, over: Partial<ProductSheetRow> = {}): ProductSheetRow => ({
  sku,
  is_active: true,
  name: `Produto ${sku}`,
  short_description: "",
  base_price_q: 1000,
  unit: "un",
  fiscal: { profile: "", ncm: "", cest: "", origin: "0" },
  fiscal_warnings: [],
  revisions: {
    name: `r-${sku}-name`,
    short_description: `r-${sku}-short`,
    base_price_q: `r-${sku}-price`,
    unit: `r-${sku}-unit`,
    "fiscal.profile": `r-${sku}-profile`,
    "fiscal.ncm": `r-${sku}-ncm`,
    "fiscal.cest": `r-${sku}-cest`,
    "fiscal.origin": `r-${sku}-origin`,
  },
  ...over,
});

describe("colar de planilha no tabelão de produtos", () => {
  it("desce pelas linhas e anda pelas colunas a partir da célula focada", () => {
    const edits = pasteBlock(
      "12,50\tsim\tProdução própria\t1905.90.90\n8,00\tnão\tproducao_propria\t19059090",
      { skus: ["A", "B", "C"], sku: "A", column: "price" },
      choices,
    );
    expect(edits).toEqual([
      { key: "A|price", value: "12,50" },
      { key: "A|by_weight", value: true },
      { key: "A|profile", value: "producao_propria" },
      { key: "A|ncm", value: "19059090" },
      { key: "B|price", value: "8,00" },
      { key: "B|by_weight", value: false },
      { key: "B|profile", value: "producao_propria" },
      { key: "B|ncm", value: "19059090" },
    ]);
  });

  it("ignora o que não serve à coluna em vez de apagar", () => {
    expect(
      pasteBlock("perfil inventado", { skus: ["A"], sku: "A", column: "profile" }, choices),
    ).toEqual([]);
    expect(
      pasteBlock("9\n", { skus: ["A"], sku: "A", column: "origin" }, choices),
    ).toEqual([]);
  });
});

describe("validação na hora", () => {
  it("aponta a célula: nome vazio, preço torto e fiscal incompleto", () => {
    const draft = {
      [sheetKey("A", "name")]: " ",
      [sheetKey("A", "price")]: "abc",
      [sheetKey("A", "ncm")]: "1905",
    };
    expect(rowProblems(row("A"), draft, profiles)).toEqual({
      name: "Informe o nome.",
      price: "Preço inválido.",
      profile: "Escolha o perfil fiscal.",
      ncm: "O NCM tem 8 dígitos.",
    });
  });

  it("o perfil com substituição tributária pede o CEST", () => {
    const draft = {
      [sheetKey("A", "profile")]: "revenda_st",
      [sheetKey("A", "ncm")]: "21069090",
    };
    expect(rowProblems(row("A"), draft, profiles)).toEqual({
      cest: "Este perfil pede o CEST.",
    });
  });
});

describe("o lote", () => {
  it("leva só o que mudou, com a revisão de cada folha, e segura a linha com erro", () => {
    const draft = {
      [sheetKey("A", "name")]: "Pão novo",
      [sheetKey("A", "price")]: "10,00",
      [sheetKey("A", "by_weight")]: true,
      [sheetKey("A", "ncm")]: "19059090",
      [sheetKey("A", "profile")]: "producao_propria",
      [sheetKey("B", "ncm")]: "123",
    };
    const result = buildRowPatches([row("A"), row("B")], draft, profiles);
    expect(result.blocked).toEqual(["B"]);
    expect(result.patches).toEqual([
      {
        sku: "A",
        patch: {
          name: "Pão novo",
          unit: "kg",
          fiscal: { profile: "producao_propria", ncm: "19059090" },
        },
        base_revisions: {
          name: "r-A-name",
          unit: "r-A-unit",
          "fiscal.profile": "r-A-profile",
          "fiscal.ncm": "r-A-ncm",
        },
      },
    ]);
  });
});
