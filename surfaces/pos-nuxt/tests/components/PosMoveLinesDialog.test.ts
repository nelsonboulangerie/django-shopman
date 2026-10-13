import { afterEach, describe, expect, it } from "vitest";
import { enableAutoUnmount } from "@vue/test-utils";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosMoveLinesDialog from "~/components/PosMoveLinesDialog.vue";

enableAutoUnmount(afterEach);

// O DIÁLOGO "TRANSFERIR ITENS" (dono, 13/10/2026): diz de onde os itens saem, e o
// exemplo do campo da comanda nova é o formato que o servidor aceita (hífen, nunca barra).
function props(overrides: Record<string, unknown> = {}) {
  return {
    open: true,
    tabDisplay: "13",
    items: [{ line_id: "L1", sku: "PAO", name: "Pão", qty: 1, price_q: 500, notes: "" }],
    suggestedSplitRef: "13-2",
    otherTabs: [],
    capability: null,
    busy: false,
    ...overrides,
  };
}

describe("PosMoveLinesDialog", () => {
  it("diz de qual comanda os itens saem, sem travessão", async () => {
    await mountSuspended(PosMoveLinesDialog, { props: props(), attachTo: document.body });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(document.body.textContent).toContain("Da comanda #13.");
    expect(document.body.textContent).not.toContain("—");
  });

  it("sem outra comanda aberta, abre na comanda nova com o exemplo de hífen", async () => {
    // Como na página: o diálogo nasce fechado e abre.
    const wrapper = await mountSuspended(PosMoveLinesDialog, { props: props({ open: false }), attachTo: document.body });
    await wrapper.setProps({ open: true });
    await new Promise((resolve) => setTimeout(resolve, 0));
    const input = document.body.querySelector<HTMLInputElement>("[data-pos-move-split-ref]");
    const field = input?.tagName === "INPUT" ? input : input?.querySelector("input");
    expect(field?.getAttribute("placeholder")).toBe("Ex.: 13-2");
    expect(document.body.textContent).not.toContain("1007/2");
  });
});
