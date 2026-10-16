import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";

import OperatorBulkBar from "../../app/components/OperatorBulkBar.vue";
import OperatorPageHeader from "../../app/components/OperatorPageHeader.vue";
import {
  bulkActionTitle,
  bulkCountLabel,
  bulkGroups,
  bulkSelectionLabel,
} from "../../app/presentation/bulkBar";

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

const calls: string[] = [];
const items = [
  [
    { label: "Pausar", icon: "i-lucide-pause", onSelect: () => calls.push("Pausar") },
    { label: "Ativar", icon: "i-lucide-play", onSelect: () => calls.push("Ativar") },
  ],
  [
    { label: "Ocultar", icon: "i-lucide-eye-off", onSelect: () => calls.push("Ocultar") },
    { label: "Exibir", icon: "i-lucide-eye", disabled: true, reason: "Já está à vista." },
  ],
  { label: "Preço…", icon: "i-lucide-tag", panel: "price", open: false },
];

const bar = () => document.querySelector<HTMLElement>("[data-operator-bulk-bar]")!;

describe("as frases da barra de seleção", () => {
  it("diz quantos e em que recorte", () => {
    expect(bulkCountLabel(1)).toBe("1 selecionado");
    expect(bulkSelectionLabel(3, "Rústicos")).toBe("3 selecionados em Rústicos");
    expect(bulkSelectionLabel(2)).toBe("2 selecionados");
    expect(bulkSelectionLabel(0, "", "Toque nos pedidos para marcar")).toBe("Toque nos pedidos para marcar");
    expect(bulkActionTitle({ label: "Exibir", disabled: true, reason: "Já está à vista." })).toBe(
      "Exibir: Já está à vista.",
    );
    expect(bulkGroups(items).map((group) => group.length)).toEqual([2, 2, 1]);
  });
});

describe("OperatorBulkBar", () => {
  it("na mesa: ordem fixa, pares opostos num grupo com o mesmo peso, × no fim", async () => {
    calls.length = 0;
    mounted = await mountSuspended(OperatorBulkBar, {
      attachTo: document.body,
      props: { count: 2, scope: "Rústicos", items },
      slots: { lead: () => h("span", { "data-lead": "" }, "Canal") },
    });
    const text = bar().textContent!.replace(/\s+/g, " ");
    expect(text.indexOf("2 selecionados em Rústicos")).toBeLessThan(text.indexOf("Canal"));
    expect(text.indexOf("Canal")).toBeLessThan(text.indexOf("Pausar"));
    expect(text.indexOf("Ativar")).toBeLessThan(text.indexOf("Ocultar"));
    expect(text.indexOf("Exibir")).toBeLessThan(text.indexOf("Preço"));

    const groups = [...bar().querySelectorAll("[data-operator-bulk-group]")];
    expect(groups).toHaveLength(2);
    const buttons = [...bar().querySelectorAll<HTMLButtonElement>("[data-operator-bulk-action]")];
    // O mesmo peso: todos `outline` neutros (nenhum ghost, nenhum solid sem `primary`).
    const classes = buttons.map((button) => button.className);
    expect(new Set(classes.map((c) => c.includes("ring") && !c.includes("bg-primary")))).toEqual(new Set([true]));
    const exibir = buttons.find((button) => button.textContent?.includes("Exibir"))!;
    expect(exibir.disabled).toBe(true);
    expect(exibir.getAttribute("title")).toBe("Exibir: Já está à vista.");

    buttons.find((button) => button.textContent?.includes("Pausar"))!.click();
    expect(calls).toEqual(["Pausar"]);

    const clear = bar().querySelector<HTMLButtonElement>("[data-operator-bulk-clear]")!;
    expect(clear.getAttribute("aria-label")).toBe("Limpar seleção");
    expect(bar().lastElementChild?.lastElementChild).toBe(clear);
    clear.click();
    expect(mounted.emitted("clear")).toHaveLength(1);
  });

  it("Esc limpa a seleção", async () => {
    mounted = await mountSuspended(OperatorBulkBar, { attachTo: document.body, props: { count: 1, items } });
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", cancelable: true }));
    expect(mounted.emitted("clear")).toHaveLength(1);
  });

  it("com uma lista aberta, o Esc é dela e não limpa a seleção", async () => {
    mounted = await mountSuspended(OperatorBulkBar, { attachTo: document.body, props: { count: 1, items } });
    const listbox = document.createElement("div");
    listbox.setAttribute("role", "listbox");
    const option = document.createElement("button");
    listbox.append(option);
    document.body.append(listbox);
    const event = new KeyboardEvent("keydown", { key: "Escape", code: "Escape", bubbles: true, cancelable: true });
    option.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
    expect(mounted.emitted("clear")).toBeUndefined();
  });

  it("na base: a superfície invertida da ação na base, só abaixo do lg, com o nome do modo", async () => {
    mounted = await mountSuspended(OperatorBulkBar, {
      attachTo: document.body,
      props: {
        count: 0,
        empty: "Toque nos pedidos para marcar",
        items,
        placement: "base",
        clearLabel: "Sair da seleção",
      },
    });
    expect(bar().tagName).toBe("FOOTER");
    expect(bar().className).toContain("lg:hidden");
    expect(bar().hasAttribute("data-focus-obstruction")).toBe(true);
    expect(bar().querySelector("[data-operator-bulk-surface]")!.className).toContain("bg-inverted");
    // Sobre a superfície invertida nada é `ghost`: cada controle leva o próprio fundo.
    expect(bar().querySelector("[data-operator-bulk-clear]")!.className).not.toContain("bg-transparent");
    expect(bar().textContent).toContain("Toque nos pedidos para marcar");
    expect(bar().querySelector("[data-operator-bulk-clear]")!.getAttribute("aria-label")).toBe("Sair da seleção");
    // Uma escuta só para o Esc: a da mesa.
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", code: "Escape", cancelable: true }));
    expect(mounted.emitted("clear")).toBeUndefined();
  });

  it("no cabeçalho, a seleção toma o lugar da toolbar do lg para cima", async () => {
    const Host = defineComponent({
      setup: () => () =>
        h(OperatorPageHeader, { title: "Catálogo" }, {
          filters: () => h("span", { "data-filters": "" }, "Filtros"),
          selection: () => h(OperatorBulkBar, { count: 2, items }),
        }),
    });
    mounted = await mountSuspended(Host, { attachTo: document.body });
    const selection = document.querySelector<HTMLElement>("[data-page-header-selection]")!;
    expect(selection.className).toContain("max-lg:hidden");
    const toolbar = document.querySelector<HTMLElement>("[data-filters]")!.closest<HTMLElement>("[data-page-header-filters]")!
      .parentElement!.closest<HTMLElement>(".lg\\:hidden");
    expect(toolbar).not.toBeNull();
  });
});
