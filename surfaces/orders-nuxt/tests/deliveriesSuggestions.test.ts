// As sugestões da casa na página Entregas (ride_plan, F5): cotação em duas linhas,
// quem chega depois, o que a tela esconde e as letras que as sugestões aceitas pegam.
import { describe, expect, it } from "vitest";

import {
  callAllLabel,
  ridesFromSuggestions,
  suggestionLate,
  suggestionOrder,
  suggestionQuoteLines,
  suggestionsHeadline,
  visibleSuggestions,
  type RideSuggestion,
} from "~/presentation/deliveries";

const suggestion = (over: Partial<RideSuggestion> = {}): RideSuggestion => ({
  key: "WEB-A47+WEB-C03",
  refs: ["WEB-A47", "WEB-C03"],
  codes: ["A47", "C03"],
  places: "Gleba Palhano",
  quoted: true,
  suggested: true,
  late_code: "C03",
  late_minutes: 6,
  together_q: 1100,
  minutes: 18,
  km: 7.4,
  with_return: false,
  separate_q: 1700,
  saving_q: 600,
  ...over,
});

describe("a cotação da sugestão", () => {
  it("vem em duas linhas, a junta em destaque com o ✔", () => {
    expect(suggestionQuoteLines(suggestion())).toEqual([
      { text: "Juntas: R$ 11,00 · 18 min · 7,4 km ✔", strong: true },
      { text: "Separadas sairiam R$ 17,00", strong: false },
    ]);
  });

  it("diz ida e volta quando a corrida volta à loja", () => {
    expect(suggestionQuoteLines(suggestion({ with_return: true }))[0]!.text).toBe(
      "Juntas: R$ 11,00 · 18 min · 7,4 km · ida e volta ✔",
    );
  });

  it("sem cotação não inventa linha", () => {
    expect(suggestionQuoteLines(suggestion({ quoted: false, together_q: null, separate_q: null }))).toEqual([]);
  });

  it("diz quem chega depois e a ordem", () => {
    expect(suggestionLate(suggestion())).toBe("C03 chega uns 6 min depois.");
    expect(suggestionLate(suggestion({ late_minutes: 0 }))).toBe("");
    expect(suggestionOrder(["A47", "C03"])).toBe("Ordem: A47, depois C03.");
    expect(suggestionOrder(["B12", "D14", "E02"])).toBe("Ordem: B12, D14, depois E02.");
  });
});

describe("o cartão das sugestões", () => {
  const second = suggestion({
    key: "WEB-B12+WEB-D14+WEB-E02",
    refs: ["WEB-B12", "WEB-D14", "WEB-E02"],
    codes: ["B12", "D14", "E02"],
    together_q: 2030,
    separate_q: 2710,
  });

  it("soma as corridas sugeridas só quando todas cotaram", () => {
    expect(suggestionsHeadline([suggestion(), second])).toEqual({
      title: "2 corridas sugeridas: 5 pedidos.",
      lines: [
        { text: "Juntas: R$ 31,30 ✔", strong: true },
        { text: "Separadas sairiam R$ 44,10", strong: false },
      ],
    });
    const unquoted = { ...second, quoted: false, suggested: false, together_q: null, separate_q: null };
    expect(suggestionsHeadline([suggestion(), unquoted]).lines).toEqual([]);
    expect(suggestionsHeadline([suggestion()]).title).toBe("1 corrida sugerida: 2 pedidos.");
  });

  it("chama todas só com todas marcadas", () => {
    expect(callAllLabel([suggestion(), second])).toBe("Chamar as 2 corridas");
    expect(callAllLabel([suggestion(), { ...second, suggested: false }])).toBe("");
    expect(callAllLabel([suggestion()])).toBe("");
  });

  it("esconde a sugestão dispensada e a que tem pedido já numa corrida", () => {
    const list = [suggestion(), second];
    expect(visibleSuggestions(list, [], [suggestion().key])).toEqual([second]);
    expect(visibleSuggestions(list, [{ number: 1, refs: ["WEB-D14"] }], [])).toEqual([suggestion()]);
  });

  it("aceitar soma corridas com as próximas letras livres, sem apagar as que existem", () => {
    const editing = [{ number: 1, refs: ["WEB-X"] }];
    expect(ridesFromSuggestions([suggestion(), second], [1, 2, 3], editing)).toEqual([
      { number: 2, refs: ["WEB-A47", "WEB-C03"] },
      { number: 3, refs: ["WEB-B12", "WEB-D14", "WEB-E02"] },
    ]);
    expect(ridesFromSuggestions([suggestion(), second], [1, 2], editing)).toBeNull();
  });
});
