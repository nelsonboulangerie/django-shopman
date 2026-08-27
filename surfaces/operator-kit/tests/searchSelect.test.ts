// A busca do SearchSelect é o que decide se o operador acha o insumo com o
// fornecedor esperando no balcão. Os casos aqui são os do balcão: nome parcial,
// SKU decorado, acento que ninguém digita e caixa que ninguém respeita.
import { describe, expect, it } from "vitest";

import {
  filterOptions,
  highlightForValue,
  matchesQuery,
  moveHighlight,
  normalizeSearchText,
  searchTerms,
  selectedLabel,
} from "../app/presentation/searchSelect";
import type { SearchSelectOption } from "../app/types/searchSelect";

const options: SearchSelectOption[] = [
  { value: "FARINHA-T65", label: "Farinha T65", hint: "FARINHA-T65 · kg" },
  { value: "FARINHA-INT", label: "Farinha Integral", hint: "FARINHA-INT · kg" },
  { value: "ACUCAR-CRISTAL", label: "Açúcar Cristal", hint: "ACUCAR-CRISTAL · kg" },
  { value: "MANTEIGA-SG", label: "Manteiga sem sal", hint: "MANTEIGA-SG · kg" },
  { value: "LEITE-INT", label: "Leite Integral", hint: "LEITE-INT · l" },
];

describe("normalizeSearchText", () => {
  it("dobra acento e caixa", () => {
    expect(normalizeSearchText("Açúcar Cristal")).toBe("acucar cristal");
  });

  it("aguenta string vazia e nula sem quebrar", () => {
    expect(normalizeSearchText("")).toBe("");
    expect(normalizeSearchText(undefined as unknown as string)).toBe("");
  });

  it("preserva a letra e apaga só o acento", () => {
    expect(normalizeSearchText("Pão Brioche")).toBe("pao brioche");
  });
});

describe("searchTerms", () => {
  it("parte a query em termos e ignora espaço sobrando", () => {
    expect(searchTerms("  farinha   t65 ")).toEqual(["farinha", "t65"]);
  });

  it("query vazia não tem termo", () => {
    expect(searchTerms("   ")).toEqual([]);
  });
});

describe("matchesQuery", () => {
  const farinha = options[0]!;

  it("acha pelo nome", () => {
    expect(matchesQuery(farinha, "farinha")).toBe(true);
  });

  it("acha pelo SKU, que mora na dica", () => {
    expect(matchesQuery(farinha, "T65")).toBe(true);
  });

  it("ignora a caixa", () => {
    expect(matchesQuery(farinha, "FARINHA")).toBe(true);
    expect(matchesQuery(farinha, "fArInHa")).toBe(true);
  });

  it("acha sem acento o que está acentuado", () => {
    expect(matchesQuery(options[2]!, "acucar")).toBe(true);
  });

  it("acha com acento o que está acentuado", () => {
    expect(matchesQuery(options[2]!, "açúcar")).toBe(true);
  });

  it("termos em qualquer ordem, cada um num campo diferente", () => {
    // "t65" vem da dica, "farinha" do rótulo: E entre termos, OU entre campos.
    expect(matchesQuery(farinha, "t65 farinha")).toBe(true);
  });

  it("um termo que não bate derruba o casamento inteiro", () => {
    expect(matchesQuery(farinha, "farinha integral")).toBe(false);
  });

  it("query vazia casa com tudo — a lista abre inteira", () => {
    expect(matchesQuery(farinha, "")).toBe(true);
    expect(matchesQuery(farinha, "   ")).toBe(true);
  });

  it("opção sem dica não quebra a busca", () => {
    expect(matchesQuery({ value: "X", label: "Fermento" }, "fermento")).toBe(true);
    expect(matchesQuery({ value: "X", label: "Fermento" }, "X")).toBe(false);
  });
});

describe("filterOptions", () => {
  it("estreita conforme se digita", () => {
    expect(filterOptions(options, "farinha").map((o) => o.value)).toEqual([
      "FARINHA-T65",
      "FARINHA-INT",
    ]);
    expect(filterOptions(options, "farinha int").map((o) => o.value)).toEqual(["FARINHA-INT"]);
  });

  it("busca por SKU chega direto no insumo", () => {
    expect(filterOptions(options, "MANTEIGA-SG").map((o) => o.value)).toEqual(["MANTEIGA-SG"]);
  });

  it("um pedaço do SKU também serve", () => {
    expect(filterOptions(options, "-int").map((o) => o.value)).toEqual([
      "FARINHA-INT",
      "LEITE-INT",
    ]);
  });

  it("query vazia devolve a lista inteira, na ordem original", () => {
    expect(filterOptions(options, "")).toEqual(options);
  });

  it("nada encontrado é lista vazia, não erro", () => {
    expect(filterOptions(options, "chocolate")).toEqual([]);
  });

  it("preserva a ordem em que o app mandou", () => {
    expect(filterOptions(options, "kg").map((o) => o.value)).toEqual([
      "FARINHA-T65",
      "FARINHA-INT",
      "ACUCAR-CRISTAL",
      "MANTEIGA-SG",
    ]);
  });
});

describe("moveHighlight", () => {
  it("desce e sobe dentro da lista", () => {
    expect(moveHighlight(0, 1, 5)).toBe(1);
    expect(moveHighlight(2, -1, 5)).toBe(1);
  });

  it("volta pelas pontas", () => {
    expect(moveHighlight(4, 1, 5)).toBe(0);
    expect(moveHighlight(0, -1, 5)).toBe(4);
  });

  it("sem destaque, ↓ vai para o primeiro e ↑ para o último", () => {
    expect(moveHighlight(-1, 1, 5)).toBe(0);
    expect(moveHighlight(-1, -1, 5)).toBe(4);
  });

  it("lista vazia não tem para onde andar", () => {
    expect(moveHighlight(0, 1, 0)).toBe(-1);
  });
});

describe("highlightForValue", () => {
  it("abre com o destaque em cima do que já está escolhido", () => {
    expect(highlightForValue(options, "ACUCAR-CRISTAL")).toBe(2);
  });

  it("sem nada escolhido, começa no primeiro", () => {
    expect(highlightForValue(options, "")).toBe(0);
  });

  it("valor que sumiu da lista cai no primeiro, não em -1", () => {
    expect(highlightForValue(options, "INSUMO-QUE-SAIU")).toBe(0);
  });

  it("lista vazia não destaca nada", () => {
    expect(highlightForValue([], "FARINHA-T65")).toBe(-1);
  });
});

describe("selectedLabel", () => {
  it("mostra o rótulo do que está escolhido", () => {
    expect(selectedLabel(options, "LEITE-INT")).toBe("Leite Integral");
  });

  it("nada escolhido é campo vazio (o placeholder fala)", () => {
    expect(selectedLabel(options, "")).toBe("");
  });

  it("valor órfão mostra o próprio valor, para o operador ver o que está lá", () => {
    expect(selectedLabel(options, "SUMIU")).toBe("SUMIU");
  });
});
