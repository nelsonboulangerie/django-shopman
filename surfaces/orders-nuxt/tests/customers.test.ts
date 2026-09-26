import { describe, expect, it } from "vitest";

import {
  listQueryFromRoute,
  mergePair,
  routeQueryFromList,
  suggestedKeeper,
} from "../app/presentation/customers";

describe("listQueryFromRoute", () => {
  it("lê busca, filtro e página da URL", () => {
    expect(listQueryFromRoute({ q: " maria ", filter: "no_phone", page: "3" })).toEqual({ q: "maria", filter: "no_phone", page: 3 });
  });

  it("filtro desconhecido e página inválida voltam ao padrão", () => {
    expect(listQueryFromRoute({ filter: "hackers", page: "-2" })).toEqual({ q: "", filter: "all", page: 1 });
    expect(listQueryFromRoute({ page: "abc" }).page).toBe(1);
  });

  it("aceita valor repetido na URL, usando o primeiro", () => {
    expect(listQueryFromRoute({ filter: ["ifood", "no_phone"] }).filter).toBe("ifood");
  });
});

describe("routeQueryFromList", () => {
  it("URL limpa quando tudo está no padrão", () => {
    expect(routeQueryFromList({ q: "", filter: "all", page: 1 })).toEqual({});
  });

  it("volta pela mesma URL", () => {
    const query = { q: "ana", filter: "possible_duplicates" as const, page: 2 };
    expect(listQueryFromRoute(routeQueryFromList(query))).toEqual(query);
  });
});

describe("suggestedKeeper", () => {
  const balcao = { ref: "CLI-1", phone_display: "(43) 99999-0000", source_label: "Balcão" };
  const ifood = { ref: "IF-1", phone_display: "", source_label: "iFood" };
  const ifoodWithPhone = { ...ifood, phone_display: "(43) 98888-0000" };

  it("fica quem tem telefone, dos dois lados", () => {
    expect(suggestedKeeper(ifood, balcao)).toBe("other");
    expect(suggestedKeeper(balcao, ifood)).toBe("current");
  });

  it("empate no telefone: fica quem não veio do iFood", () => {
    expect(suggestedKeeper(ifoodWithPhone, balcao)).toBe("other");
    expect(suggestedKeeper({ ...balcao, phone_display: "" }, ifood)).toBe("current");
  });

  it("empate total: fica o cadastro aberto na tela", () => {
    expect(suggestedKeeper(ifood, { ...ifood, ref: "IF-2" })).toBe("current");
  });
});

describe("mergePair", () => {
  it("quem fica é o target; o outro é o source", () => {
    expect(mergePair("CLI-1", "IF-1", "current")).toEqual({ source_ref: "IF-1", target_ref: "CLI-1" });
    expect(mergePair("CLI-1", "IF-1", "other")).toEqual({ source_ref: "CLI-1", target_ref: "IF-1" });
  });
});
