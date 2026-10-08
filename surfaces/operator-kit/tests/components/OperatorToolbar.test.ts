import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { h } from "vue";

import OperatorToolbar from "../../app/components/OperatorToolbar.vue";

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

describe("OperatorToolbar, a barra canônica sobre o DashboardToolbar oficial", () => {
  it("põe left e right nas colunas do oficial e mantém a cor do tema", async () => {
    mounted = await mountSuspended(OperatorToolbar, {
      attachTo: document.body,
      slots: {
        left: () => h("span", { "data-test": "esquerda" }, "Filtros"),
        right: () => h("span", { "data-test": "direita" }, "Ações"),
      },
    });

    const root = document.body.querySelector<HTMLElement>("[data-operator-toolbar]")!;
    expect(root.tagName).toBe("DIV");
    expect(root.getAttribute("data-slot")).toBe("root");
    // A pele é do tema (app.config.ts), não da peça.
    expect(root.className).toContain("bg-card");
    expect(
      root.querySelector('[data-slot="left"] [data-test="esquerda"]')?.textContent,
    ).toBe("Filtros");
    expect(
      root.querySelector('[data-slot="right"] [data-test="direita"]')?.textContent,
    ).toBe("Ações");
  });

  it("o slot padrão ocupa a barra inteira, como no oficial", async () => {
    mounted = await mountSuspended(OperatorToolbar, {
      attachTo: document.body,
      slots: { default: () => h("span", { "data-test": "tudo" }, "Barra") },
    });

    const root = document.body.querySelector<HTMLElement>("[data-operator-toolbar]")!;
    expect(root.querySelector('[data-test="tudo"]')?.textContent).toBe("Barra");
    expect(root.querySelector('[data-slot="left"]')).toBeNull();
    expect(root.querySelector('[data-slot="right"]')).toBeNull();
  });

  it('as="footer" vira <footer> e os atributos chegam ao elemento', async () => {
    mounted = await mountSuspended(OperatorToolbar, {
      attachTo: document.body,
      props: { as: "footer" },
      attrs: {
        class: "py-3",
        "data-board-toolbar": "",
        "aria-label": "Ações do quadro",
      },
      slots: { right: () => h("button", { type: "button" }, "Salvar") },
    });

    const root = document.body.querySelector<HTMLElement>("[data-operator-toolbar]")!;
    expect(root.tagName).toBe("FOOTER");
    expect(root.hasAttribute("data-board-toolbar")).toBe(true);
    expect(root.getAttribute("aria-label")).toBe("Ações do quadro");
    expect(root.className).toContain("py-3");
    expect(root.className).toContain("bg-card");
    expect(root.querySelector('[data-slot="right"] button')?.textContent).toBe("Salvar");
  });
});
