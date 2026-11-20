import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { h } from "vue";

import OperatorPageHeader from "../../app/components/OperatorPageHeader.vue";

// O aviso da tela vem depois de TODAS as barras do topo e é o primeiro item do conteúdo,
// em todo tamanho (dono, 20/11/2026, DEV-2026-063). Trava do lado do kit: montado com a
// barra, os controles, os recortes, os filtros, a seleção e as abas do `#below`, o bloco
// de avisos vem depois de cada um na ordem do documento, e nada no caminho dele reordena
// pelo CSS (`order`), então a ordem visual é a mesma. O lado dos apps (barra montada fora
// do cabeçalho) é o `guardrails.alertsAfterBars.test.ts`.

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;
afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

const BARS = {
  navbar: "[data-operator-page-header]",
  actions: "[data-test-actions]",
  filtersPrimary: "[data-test-filters-primary]",
  filters: "[data-test-filters]",
  filterPanel: "[data-test-filter-panel]",
  selection: "[data-page-header-selection]",
  below: "[data-test-below-tabs]",
} as const;

async function mountWithEveryBar() {
  mounted = await mountSuspended(OperatorPageHeader, {
    attachTo: document.body,
    props: {
      title: "Pedidos",
      search: false,
      inbox: false,
      alerts: [{ id: "answer", color: "warning", title: "Ana espera a resposta da equipe" }],
    },
    slots: {
      actions: () => h("button", { "data-test-actions": "" }, "Som"),
      "filters-primary": () => h("div", { "data-test-filters-primary": "" }, "Todos"),
      filters: () => h("div", { "data-test-filters": "" }, "Canal"),
      "filter-panel": () => h("button", { "data-test-filter-panel": "" }, "Filtros"),
      selection: () => h("div", { "data-test-selection": "" }, "2 marcados"),
      below: () => h("div", { role: "tablist", "data-test-below-tabs": "" }, "Novos · Em preparo · Prontos"),
      feedback: () => h("p", { "data-test-feedback": "" }, "iFood fechado"),
    },
  });
}

function follows(earlier: Element, later: Element): boolean {
  return Boolean(earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING);
}

describe("OperatorPageHeader: o aviso depois de todas as barras do topo", () => {
  it("o bloco de avisos vem depois da barra, dos controles, dos filtros, da seleção e das abas do #below", async () => {
    await mountWithEveryBar();
    const alerts = document.querySelector("[data-page-header-alerts]")!;
    expect(alerts).not.toBeNull();
    for (const [name, selector] of Object.entries(BARS)) {
      const bar = document.querySelector(selector);
      expect(bar, `${name} montada`).not.toBeNull();
      expect(follows(bar!, alerts), `aviso depois de ${name}`).toBe(true);
      expect(alerts.contains(bar!), `${name} fora do aviso`).toBe(false);
    }
  });

  it("depois do aviso só o retorno contextual (`#feedback`), nunca uma barra", async () => {
    await mountWithEveryBar();
    const landmark = document.querySelector("[data-operator-page-header-landmark]")!;
    const children = [...landmark.children];
    const at = children.findIndex((el) => el.hasAttribute("data-page-header-alerts"));
    expect(at).toBeGreaterThan(0);
    const after = children.slice(at + 1);
    expect(after.map((el) => el.hasAttribute("data-page-header-feedback"))).toEqual([true]);
  });

  it("a ordem visual é a do documento: o invólucro é `contents` e nada reordena pelo CSS", async () => {
    await mountWithEveryBar();
    const landmark = document.querySelector<HTMLElement>("[data-operator-page-header-landmark]")!;
    expect(landmark.classList.contains("contents")).toBe(true);
    // As linhas do cabeçalho são filhas diretas do invólucro (`contents`): na coluna da
    // página, é a ordem delas que decide o que fica em cima.
    const ordered = [landmark, ...(landmark.children as HTMLCollectionOf<HTMLElement>)];
    const reordering = ordered.filter(
      (el) =>
        [...el.classList].some((name) => /(^|:)-?order-|(^|:)flex-(col|row)-reverse$/.test(name)) ||
        el.style.order !== "",
    );
    expect(reordering.map((el) => el.outerHTML.slice(0, 80))).toEqual([]);
  });
});
