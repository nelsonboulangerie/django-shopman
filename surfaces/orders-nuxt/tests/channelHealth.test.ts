import { describe, expect, it } from "vitest";

import { itemAction, orderedItems, pairUrl, previewHref } from "../app/presentation/channelHealth";
import { filtersFromQuery } from "../app/presentation/catalogFilters";
import type { ChannelHealthItem, ChannelHealthProjection } from "../app/types/channelHealth";

const bases = { djangoBase: "https://api.loja", adminBase: "https://admin.loja" };
const item = (over: Partial<ChannelHealthItem>): ChannelHealthItem => ({
  key: "k", state: "todo", label: "rótulo", hint: "", action_label: "", action_target: "", action_path: "", ...over,
});
const health = (items: ChannelHealthItem[], preview = [{ label: "Ver a tela da TV", target: "django", path: "/menuboard/tv/" }]): ChannelHealthProjection =>
  ({ ref: "tv", ready: false, summary: "", items, preview });

describe("checklist do canal — ação de cada item", () => {
  it("resolve o destino declarado pelo servidor", () => {
    expect(itemAction(item({ action_label: "Vincular", action_target: "gestor", action_path: "/channels/ifood/catalog" }), bases))
      .toEqual({ kind: "route", label: "Vincular", to: "/channels/ifood/catalog" });
    expect(itemAction(item({ action_label: "Ver integrações", action_target: "admin", action_path: "/admin/diagnostics/" }), bases))
      .toEqual({ kind: "external", label: "Ver integrações", href: "https://admin.loja/admin/diagnostics/" });
    expect(itemAction(item({ action_label: "Parear uma TV", action_target: "pair" }), bases)).toEqual({ kind: "pair", label: "Parear uma TV" });
    expect(itemAction(item({ action_label: "Escolher coleções", action_target: "collections" }), bases)?.kind).toBe("collections");
  });

  it("sem rótulo, destino desconhecido ou caminho vazio, não inventa botão", () => {
    expect(itemAction(item({}), bases)).toBeNull();
    expect(itemAction(item({ action_label: "X", action_target: "outro" }), bases)).toBeNull();
    expect(itemAction(item({ action_label: "X", action_target: "gestor" }), bases)).toBeNull();
  });

  it("pendência primeiro, na ordem do servidor", () => {
    const items = [item({ key: "a", state: "ok" }), item({ key: "b" }), item({ key: "c", state: "ok" }), item({ key: "d" })];
    expect(orderedItems(health(items)).map((i) => i.key)).toEqual(["b", "d", "a", "c"]);
  });

  it("o endereço de pareamento é a tela da TV servida pelo Django", () => {
    expect(pairUrl(health([]), bases)).toBe("https://api.loja/menuboard/tv/");
    expect(pairUrl(health([], []), bases)).toBe("");
    expect(previewHref({ label: "Ver a loja", target: "external", path: "https://loja" }, bases)).toBe("https://loja");
  });
});

describe("catálogo recortado pela URL do checklist", () => {
  it("?surface=ifood&sync=error abre só os recusados do iFood", () => {
    expect(filtersFromQuery({ surface: "ifood", sync: "error" })).toEqual({ surface: ["ifood"], sync_status: ["error"] });
  });

  it("valor que a dimensão não conhece não vira filtro", () => {
    expect(filtersFromQuery({ sync: "quebrado", outro: "x" })).toEqual({});
    expect(filtersFromQuery({})).toEqual({});
  });
});
