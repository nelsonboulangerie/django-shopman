// A regra única da barra do topo e da toolbar no celular (README do kit, "Barra do
// topo no celular" e "Toolbar no celular"; dono, 08/10/2026). A geometria a 320 e
// 390 px é travada no navegador por `tests/catalog/phone-header.spec.ts`; aqui, a
// decisão: quem ganha a vaga de ícone, o que vai para o ⋯ e em que ordem.
import { describe, expect, it } from "vitest";

import { filterBarActiveFilters } from "../app/presentation/filterBar";
import {
  PHONE_HEADER_ICON_SLOTS,
  SEARCH_PRIORITY,
  filtersButtonLabel,
  phoneHeaderControlCount,
  phoneHeaderLayout,
  type OperatorHeaderAction,
} from "../app/presentation/pageHeader";
import type { FilterDimension } from "../app/types/filters";

const act = (label: string, priority?: number): OperatorHeaderAction => ({
  label,
  icon: "i-lucide-circle",
  ...(priority === undefined ? {} : { priority }),
});

describe("phoneHeaderLayout: no máximo 2 ícones fixos, o resto no ⋯", () => {
  it("sem ações: Busca e Avisos, sem ⋯", () => {
    const layout = phoneHeaderLayout({ search: true, inbox: true, actions: [] });
    expect(layout).toEqual({ searchIcon: true, icons: [], overflow: [] });
    expect(phoneHeaderControlCount(layout, true)).toBe(2);
  });

  it("ações sem prioridade vão todas para o ⋯, na ordem declarada", () => {
    const actions = [act("Copiar link"), act("Exportar CSV"), act("Imprimir")];
    const layout = phoneHeaderLayout({ search: true, inbox: true, actions });
    expect(layout.searchIcon).toBe(true);
    expect(layout.icons).toEqual([]);
    expect(layout.overflow.map((item) => item.label)).toEqual(["Copiar link", "Exportar CSV", "Imprimir"]);
    expect(phoneHeaderControlCount(layout, true)).toBe(3);
  });

  it("uma ação de prioridade menor que a da Busca toma a vaga; a Busca vira 'Buscar' no ⋯", () => {
    const actions = [act("Atualizar"), act("Ciente de todos", SEARCH_PRIORITY - 1)];
    const layout = phoneHeaderLayout({ search: true, inbox: true, actions });
    expect(layout.searchIcon).toBe(false);
    expect(layout.icons.map((item) => item.label)).toEqual(["Ciente de todos"]);
    expect(layout.overflow.map((item) => item.label)).toEqual(["Buscar", "Atualizar"]);
  });

  it("a Busca vence quem declara prioridade maior (ou igual, por ordem)", () => {
    const layout = phoneHeaderLayout({ search: true, inbox: true, actions: [act("Compartilhar", SEARCH_PRIORITY)] });
    expect(layout.searchIcon).toBe(true);
    expect(layout.overflow.map((item) => item.label)).toEqual(["Compartilhar"]);
  });

  it("sem Avisos na barra, sobram 2 vagas", () => {
    const actions = [act("A", 1), act("B", 2), act("C", 3)];
    const layout = phoneHeaderLayout({ search: true, inbox: false, actions });
    expect(layout.icons.map((item) => item.label)).toEqual(["A", "B"]);
    expect(layout.searchIcon).toBe(false);
    expect(layout.overflow.map((item) => item.label)).toEqual(["Buscar", "C"]);
  });

  it("nunca passa de 2 ícones fixos mais o ⋯, quantas ações houver", () => {
    const actions = Array.from({ length: 9 }, (_, index) => act(`Ação ${index}`, index));
    for (const inbox of [true, false]) {
      for (const search of [true, false]) {
        const layout = phoneHeaderLayout({ search, inbox, actions });
        const fixed = (layout.searchIcon ? 1 : 0) + layout.icons.length + (inbox ? 1 : 0);
        expect(fixed).toBeLessThanOrEqual(PHONE_HEADER_ICON_SLOTS);
        expect(phoneHeaderControlCount(layout, inbox)).toBeLessThanOrEqual(PHONE_HEADER_ICON_SLOTS + 1);
        // Nenhuma ação se perde: ou é ícone, ou está no ⋯.
        const shown = [...layout.icons, ...layout.overflow].map((item) => item.label);
        for (const action of actions) expect(shown).toContain(action.label);
      }
    }
  });
});

describe("toolbar do celular", () => {
  it("o 'Filtros' diz quantos recortes estão ativos", () => {
    expect(filtersButtonLabel(0)).toBe("Filtros");
    expect(filtersButtonLabel(1)).toBe("Filtros: 1 recorte ativo");
    expect(filtersButtonLabel(3)).toBe("Filtros: 3 recortes ativos");
  });

  it("os campos da FilterBar viram recortes ativos com o rótulo do chip e o ×", () => {
    const dimensions: FilterDimension[] = [
      { id: "status", label: "Status", type: "multi-select", options: [{ value: "done", label: "Concluído" }, { value: "cancelled", label: "Cancelado" }] },
      { id: "payment", label: "Pagamento", type: "single-select", options: [{ value: "pix", label: "Pix" }] },
    ];
    let state: Record<string, string[]> = { status: ["done", "cancelled"] };
    const active = filterBarActiveFilters(dimensions, state, (next) => {
      state = next;
    });
    expect(active.map((item) => item.key)).toEqual(["status"]);
    expect(active[0]!.label).toContain("Status");
    active[0]!.remove();
    expect(state).toEqual({});
  });
});
