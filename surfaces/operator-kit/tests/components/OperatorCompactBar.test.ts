// A linha do chão: busca, sino e o ⋮ no canto, sempre o último (dono, 03/11/2026). A tela
// que tem o seu próprio ⋮ (o painel do pedido no Gestor) usa `#more`, que toma o lugar do
// menu do kit no mesmo canto; no `#identity` o ⋮ ficava antes da busca e do sino.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it } from "vitest";
import { h } from "vue";

import OperatorCompactBar from "../../app/components/OperatorCompactBar.vue";

const stubs = {
  ClientOnly: { template: "<div><slot /></div>" },
  OperatorInbox: { template: "<div data-inbox-stub />" },
  OperatorCompactSeal: { template: "<div data-seal-stub />" },
};

function order(html: string, markers: string[]) {
  return markers.map((marker) => html.indexOf(marker));
}

describe("OperatorCompactBar", () => {
  it("o ⋮ do kit fica no canto, depois da busca e do sino", async () => {
    const wrapper = await mountSuspended(OperatorCompactBar, {
      props: { title: "Pedidos", options: [{ label: "Atualizar", onSelect: () => {} }] },
      global: { stubs },
    });
    const at = order(wrapper.html(), ["data-compact-search", "data-inbox-stub", "data-compact-options"]);
    expect(at.every((i) => i >= 0)).toBe(true);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
  });

  it("#more toma o lugar do menu do kit, no mesmo canto", async () => {
    const wrapper = await mountSuspended(OperatorCompactBar, {
      props: { title: "Pedido H58", options: [{ label: "Atualizar", onSelect: () => {} }] },
      slots: {
        identity: () => h("div", { "data-identity": "" }, "H58"),
        more: () => h("button", { "data-own-more": "" }, "⋮"),
      },
      global: { stubs },
    });
    expect(wrapper.find("[data-compact-options]").exists()).toBe(false);
    const at = order(wrapper.html(), ["data-identity", "data-compact-search", "data-inbox-stub", "data-own-more"]);
    expect(at.every((i) => i >= 0)).toBe(true);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
  });

  it("#filter-panel: o filtro único fica na linha, antes da busca, do sino e do ⋮", async () => {
    const wrapper = await mountSuspended(OperatorCompactBar, {
      props: { title: "Enviados", options: [{ label: "Atualizar", onSelect: () => {} }] },
      slots: { "filter-panel": () => h("button", { "data-own-filter": "" }, "Filtros") },
      global: { stubs },
    });
    const at = order(wrapper.html(), ["data-own-filter", "data-compact-search", "data-inbox-stub", "data-compact-options"]);
    expect(at.every((i) => i >= 0)).toBe(true);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
    expect(wrapper.get("[role=group]").attributes("aria-label")).toBe("Filtros, buscar, avisos e opções: Enviados");
    // O ⋮ não ganha o item "Filtros" do painel antigo.
    expect(wrapper.html()).not.toContain("Filtros:");
  });

  it("seal-app-as-title: a linha não tem <h1>, a página traz o dela", async () => {
    const plain = await mountSuspended(OperatorCompactBar, { props: { title: "Pedidos" }, global: { stubs } });
    expect(plain.findAll("h1").map((h) => h.text())).toEqual(["Pedidos"]);
    const app = await mountSuspended(OperatorCompactBar, {
      props: { title: "Olá, Ana", sealAppAsTitle: true },
      global: { stubs },
    });
    expect(app.find("h1").exists()).toBe(false);
  });
});
