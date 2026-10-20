import { describe, expect, it } from "vitest";

import {
  FILTER_ARCHIVED,
  FILTER_PIM,
  FILTER_PUBLISHED,
  FILTER_SELLABLE,
  FILTER_STOCK,
  FILTER_SURFACE,
  FILTER_SYNC,
  FILTER_VOCATION,
  filtersFromQuery,
  serverCatalogDimensions,
  vocationPendingFilters,
} from "../app/presentation/catalogFilters";
import type { CatalogFacets, SurfaceProjection } from "../app/types/catalog";

const surface = (over: Partial<SurfaceProjection> = {}): SurfaceProjection => ({
  ref: "ifood",
  name: "iFood",
  short_name: "iFood",
  is_projection_target: true,
  sync_status: "ok",
  kind: "channel",
  transactional: true,
  icon: "",
  output_path: "",
  sync_key: "ifood",
  ...over,
});

const surfaces = [
  surface({ ref: "ifood", name: "iFood", is_projection_target: true }),
  surface({ ref: "web", name: "Site", is_projection_target: false }),
];

// Contagens como o servidor devolve: do recorte inteiro, não da página.
const facets: CatalogFacets = {
  stock: { ok: 3, low: 2, out: 1 },
  sync_status: { synced: 4, pending: 1, error: 2, never: 5 },
};

describe("serverCatalogDimensions", () => {
  it("oferece as 8 dimensões (coleção fica de fora — é o eixo das pills)", () => {
    const ids = serverCatalogDimensions(surfaces, facets).map((d) => d.id);
    expect(ids).toEqual([
      FILTER_SYNC,
      FILTER_SURFACE,
      FILTER_ARCHIVED,
      FILTER_PUBLISHED,
      FILTER_SELLABLE,
      FILTER_STOCK,
      FILTER_PIM,
      FILTER_VOCATION,
    ]);
  });

  it("sem plataforma que projeta, envio e dados sociais somem", () => {
    const ids = serverCatalogDimensions(
      [surface({ ref: "web", is_projection_target: false })],
      facets,
    ).map((d) => d.id);
    expect(ids).toEqual([
      FILTER_SURFACE,
      FILTER_ARCHIVED,
      FILTER_PUBLISHED,
      FILTER_SELLABLE,
      FILTER_STOCK,
      FILTER_VOCATION,
    ]);
  });

  it("canais e feeds vêm da lista viva de superfícies", () => {
    const dimension = serverCatalogDimensions(surfaces, facets).find(
      (d) => d.id === FILTER_SURFACE,
    )!;
    expect(dimension.options.map((o) => o.value)).toEqual(["ifood", "web"]);
    expect(dimension.options[0]!.label).toBe("iFood");
    // A superfície não tem contagem por opção: só estoque e envio têm.
    expect(dimension.options[0]!.count).toBeUndefined();
  });

  it("estoque e envio carregam as contagens do SERVIDOR", () => {
    const dimensions = serverCatalogDimensions(surfaces, facets);
    const stock = dimensions.find((d) => d.id === FILTER_STOCK)!;
    expect(
      Object.fromEntries(stock.options.map((o) => [o.value, o.count])),
    ).toEqual({ ok: 3, low: 2, out: 1 });
    const sync = dimensions.find((d) => d.id === FILTER_SYNC)!;
    expect(sync.options.map((o) => o.count)).toEqual([4, 1, 2, 5]);
  });

  it("sem contagens (primeira carga), a opção sai sem número inventado", () => {
    const stock = serverCatalogDimensions(surfaces, undefined).find(
      (d) => d.id === FILTER_STOCK,
    )!;
    expect(stock.options.every((o) => o.count === undefined)).toBe(true);
  });
});

describe("filtersFromQuery", () => {
  it("lê o recorte do checklist do canal (surface + sync)", () => {
    expect(filtersFromQuery({ surface: "ifood", sync: "error" })).toEqual({
      [FILTER_SURFACE]: ["ifood"],
      [FILTER_SYNC]: ["error"],
    });
  });

  it("lê estoque, PIM e os booleans", () => {
    expect(
      filtersFromQuery({
        stock: "out,low",
        pim_complete: "true",
        archived: "true",
        is_published: "false",
      }),
    ).toEqual({
      [FILTER_STOCK]: ["out", "low"],
      [FILTER_PIM]: ["true"],
      [FILTER_ARCHIVED]: ["true"],
      [FILTER_PUBLISHED]: ["false"],
    });
  });

  it("valor desconhecido não vira filtro que zera a tela", () => {
    expect(filtersFromQuery({ sync: "explodiu", stock: "meio" })).toEqual({});
  });
});

describe("vocação", () => {
  it("o Classificar recorta à venda e sem vocação, o mesmo critério do aviso", () => {
    expect(vocationPendingFilters()).toEqual({
      [FILTER_SELLABLE]: ["true"],
      [FILTER_VOCATION]: ["false"],
    });
  });
});
