import { expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import PosTabHeader from "~/components/PosTabHeader.vue";

it("balcão esconde entrega e data; modo encomenda emite intenção sem apagar itens", async () => {
  const w = await mountSuspended(PosTabHeader, { props: {
    salesMode: "counter", tabDisplay: "M1", hasOpenTab: true, canRename: false,
    customerName: "Ana", customerPhone: "", customerTaxId: "", customerEmail: "", customerLookup: null,
    lookupBusy: false, searchResults: [], searchBusy: false, fulfillmentType: "pickup",
    fulfillmentLabel: "Retirada", scheduleLabel: "Para hoje", scheduled: false, loading: false,
  }, global: { stubs: { PosCustomerModal: true } } });
  expect(w.text()).not.toContain("Retirada");
  expect(w.text()).not.toContain("Para hoje");
  const modeButton = (label: string) => w.findAll("button").find((b) => b.find(".sr-only").exists() && b.find(".sr-only").text() === label)!;
  // O modo ligado é o `solid` da suíte (marca `data-pos-sales-mode-active`) e diz isso ao leitor de tela; o outro não.
  expect(modeButton("Balcão").attributes("aria-pressed")).toBe("true");
  expect(modeButton("Balcão").attributes("data-pos-sales-mode-active")).toBeDefined();
  expect(modeButton("Encomendas").attributes("aria-pressed")).toBe("false");
  expect(modeButton("Encomendas").attributes("data-pos-sales-mode-active")).toBeUndefined();
  await modeButton("Encomendas").trigger("click");
  expect(w.emitted("salesModeChange")).toEqual([["order"]]);
  expect(w.emitted("clear")).toBeUndefined();
  await w.setProps({ salesMode: "order" });
  expect(w.text()).toContain("Retirada");
  expect(w.text()).toContain("Para hoje");
  expect(modeButton("Encomendas").attributes("aria-pressed")).toBe("true");
  expect(modeButton("Encomendas").attributes("data-pos-sales-mode-active")).toBeDefined();
  expect(modeButton("Balcão").attributes("data-pos-sales-mode-active")).toBeUndefined();
  w.unmount();
});

it("cliente travado (edição de encomenda): o chip diz por quê e não abre o modal", async () => {
  const reason = "O cliente da encomenda não muda na edição.";
  const w = await mountSuspended(PosTabHeader, { props: {
    salesMode: "order", tabDisplay: "", hasOpenTab: true, canRename: false,
    customerName: "Ana", customerPhone: "", customerTaxId: "", customerEmail: "", customerLookup: null,
    lookupBusy: false, searchResults: [], searchBusy: false, fulfillmentType: "pickup",
    fulfillmentLabel: "Retirada", scheduleLabel: "sáb, 04/10", scheduled: true, loading: false,
    customerLockedReason: reason,
  }, global: { stubs: { PosCustomerModal: true } } });
  const chip = w.find('[data-context-entry="customer"]');
  expect(chip.attributes("title")).toBe(reason);
  await chip.trigger("click");
  expect(w.emitted("customerLocked")).toEqual([[reason]]);
  // F6 chega pelo `openCustomer` exposto: a mesma trava.
  (w.vm as unknown as { openCustomer: () => void }).openCustomer();
  expect(w.emitted("customerLocked")).toHaveLength(2);
  expect(w.findComponent({ name: "PosCustomerModal" }).attributes("open")).not.toBe("true");
  w.unmount();
});

it("a comanda que nasceu de uma transferência mostra o selo do rastro (dono, T1=1)", async () => {
  const base = {
    salesMode: "counter", tabDisplay: "13-2", hasOpenTab: true, canRename: false,
    customerName: "", customerPhone: "", customerTaxId: "", customerEmail: "", customerLookup: null,
    lookupBusy: false, searchResults: [], searchBusy: false, fulfillmentType: "pickup",
    fulfillmentLabel: "Retirada", scheduleLabel: "Para hoje", scheduled: false, loading: false,
  };
  const w = await mountSuspended(PosTabHeader, {
    props: { ...base, transferredFrom: { label: "Transf. da #13", title: "Transferida da comanda #13" } },
    global: { stubs: { PosCustomerModal: true } },
  });
  const seal = w.find("[data-pos-tab-transferred-from]");
  expect(seal.text()).toBe("Transf. da #13");
  expect(seal.attributes("title")).toBe("Transferida da comanda #13");
  w.unmount();
  const plain = await mountSuspended(PosTabHeader, { props: base, global: { stubs: { PosCustomerModal: true } } });
  expect(plain.find("[data-pos-tab-transferred-from]").exists()).toBe(false);
  plain.unmount();
});
