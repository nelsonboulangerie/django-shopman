import { afterEach, describe, expect, it } from "vitest";
import { enableAutoUnmount } from "@vue/test-utils";
import { mountSuspended } from "@nuxt/test-utils/runtime";

import PosMoveLinesDialog from "~/components/PosMoveLinesDialog.vue";

enableAutoUnmount(afterEach);

// TRANSFERIR, A AÇÃO ÚNICA (dono, N=1, 13/10/2026): um campo "Para qual comanda?" que já
// nasce com a comanda nova pré-nomeada; Enter confirma; bipar ou escolher uma comanda em
// uso troca o destino; o botão diz o resultado em palavras.
const items = [
  { line_id: "L1", sku: "CR", name: "Croissant", qty: 2, price_q: 1150, notes: "" },
  { line_id: "L2", sku: "PC", name: "Pain au chocolat", qty: 1, price_q: 1290, notes: "" },
];
const otherTabs = [{ ref: "00000012", display_ref: "12", session_key: "s12", state: "in_use", customer_name: "Ana Souza" }];

function props(overrides: Record<string, unknown> = {}) {
  return {
    open: false,
    tabDisplay: "13",
    sourceSessionKey: "s13",
    items,
    suggestedNewTabRef: "13-2",
    otherTabs,
    capability: null,
    busy: false,
    ...overrides,
  };
}

async function openDialog(overrides: Record<string, unknown> = {}) {
  // Como na página: o diálogo nasce fechado e abre.
  const wrapper = await mountSuspended(PosMoveLinesDialog, { props: props(overrides), attachTo: document.body });
  await wrapper.setProps({ open: true });
  await new Promise((resolve) => setTimeout(resolve, 0));
  return wrapper;
}
const input = () => document.body.querySelector<HTMLInputElement>("[data-pos-move-destination] input, input[data-pos-move-destination]")!;
const cta = () => document.body.querySelector<HTMLButtonElement>("[data-pos-move-submit]")!;

describe("PosMoveLinesDialog — Transferir", () => {
  it("diz de onde saem e o que vai, sem travessão", async () => {
    await openDialog({ preselected: ["L1"] });
    expect(document.body.textContent).toContain("Da comanda #13.");
    expect(document.body.querySelector("[data-pos-move-summary]")?.textContent).toContain("2 itens: 2× Croissant");
    expect(document.body.textContent).not.toContain("—");
  });

  it("a ação padrão já está pronta: comanda nova pré-nomeada, e o Enter confirma", async () => {
    const wrapper = await openDialog({ preselected: ["L1"] });
    expect(input().value).toBe("13-2");
    expect(cta().textContent).toContain("Separar 2 itens na comanda nova 13-2");
    input().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("submit")?.[0]).toEqual([{ mode: "split", lineIds: ["L1"], toTabRef: "13-2" }]);
  });

  it("sem nada marcado vai tudo, e a origem é liberada", async () => {
    const wrapper = await openDialog();
    expect(cta().textContent).toContain("Levar tudo para a comanda nova 13-2 e liberar a #13");
    cta().click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("submit")?.[0]).toEqual([{ mode: "split", lineIds: ["L1", "L2"], toTabRef: "13-2", closeSource: true }]);
  });

  it("bipar ou digitar uma comanda em uso troca o destino; tocar na lista também", async () => {
    const wrapper = await openDialog({ preselected: ["L2"] });
    input().value = "12";
    input().dispatchEvent(new Event("input", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(cta().textContent).toContain("Levar 1 item para a #12");
    input().value = "13-9";
    input().dispatchEvent(new Event("input", { bubbles: true }));
    await wrapper.vm.$nextTick();
    (document.body.querySelector('[data-pos-move-target="s12"]') as HTMLButtonElement).click();
    await wrapper.vm.$nextTick();
    expect(input().value).toBe("#12");
    cta().click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("submit")?.[0]).toEqual([{ mode: "transfer", lineIds: ["L2"], toSessionKey: "s12" }]);
  });

  it("barra no nome: o motivo em palavra e o botão apagado", async () => {
    const wrapper = await openDialog();
    input().value = "13/2";
    input().dispatchEvent(new Event("input", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(document.body.querySelector("[data-pos-move-destination-state]")?.textContent).toContain("Use um hífen, por exemplo 13-2.");
    expect(cta().disabled).toBe(true);
  });

  it("mesa: a ocupada leva à comanda dela, a livre abre a nova já nela (dono, M=1)", async () => {
    const spots = [
      { ref: "M4", label: "Mesa 4", short_label: "M4", area: "Salão", kind: "table" },
      { ref: "M5", label: "Mesa 5", short_label: "M5", area: "Salão", kind: "table" },
    ];
    const tabs = [{ ...otherTabs[0], seating_spot_ref: "M4" }];
    const wrapper = await openDialog({ preselected: ["L1"], otherTabs: tabs, seatingSpots: spots });
    input().value = "Mesa 4";
    input().dispatchEvent(new Event("input", { bubbles: true }));
    await wrapper.vm.$nextTick();
    expect(cta().textContent).toContain("Levar 2 itens para a Mesa 4 (#12)");
    (document.body.querySelector('[data-pos-move-spot="M5"]') as HTMLButtonElement).click();
    await wrapper.vm.$nextTick();
    expect(cta().textContent).toContain("Separar 2 itens na comanda nova 13-2 (Mesa 5)");
    cta().click();
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("submit")?.[0]).toEqual([{ mode: "split", lineIds: ["L1"], toTabRef: "13-2", seatingSpotRef: "M5" }]);
  });
});
