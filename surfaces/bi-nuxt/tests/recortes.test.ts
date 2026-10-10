// Os recortes do B.I. no formato do painel de filtros (o que o favorito guarda).
import { describe, expect, it } from "vitest";
import { filtersToPicks, picksToFilters } from "~/presentation/recortes";

describe("recortes do B.I. no painel de filtros", () => {
  it("o Todos não vira recorte", () => {
    expect(picksToFilters({ verdict: "all", collection: "" })).toEqual({});
  });

  it("cada escolha vira uma lista de um valor", () => {
    expect(picksToFilters({ verdict: "over", collection: "macios" })).toEqual({ verdict: ["over"], collection: ["macios"] });
  });

  it("de volta, a chave que falta volta a Todos e a desconhecida fica de fora", () => {
    expect(filtersToPicks({ verdict: ["short"], other: ["x"] }, ["verdict", "collection"])).toEqual({
      verdict: "short",
      collection: "all",
    });
  });

  it("ida e volta preserva o recorte", () => {
    const picks = { channel: "ifood" };
    expect(filtersToPicks(picksToFilters(picks), ["channel"])).toEqual(picks);
  });
});
