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
  await w.findAll("button").find((b) => b.text() === "Encomendas")!.trigger("click");
  expect(w.emitted("salesModeChange")).toEqual([["order"]]);
  expect(w.emitted("clear")).toBeUndefined();
  await w.setProps({ salesMode: "order" });
  expect(w.text()).toContain("Retirada");
  expect(w.text()).toContain("Para hoje");
  w.unmount();
});
