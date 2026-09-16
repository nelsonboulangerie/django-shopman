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
  const modeButton = (label: string) => w.findAll("button").find((b) => b.text() === label)!;
  // O modo ligado é CHEIO (`bg-primary`) e diz isso ao leitor de tela; o outro não.
  expect(modeButton("Balcão").attributes("aria-pressed")).toBe("true");
  expect(modeButton("Balcão").classes()).toContain("bg-primary");
  expect(modeButton("Encomendas").attributes("aria-pressed")).toBe("false");
  expect(modeButton("Encomendas").classes()).not.toContain("bg-primary");
  await modeButton("Encomendas").trigger("click");
  expect(w.emitted("salesModeChange")).toEqual([["order"]]);
  expect(w.emitted("clear")).toBeUndefined();
  await w.setProps({ salesMode: "order" });
  expect(w.text()).toContain("Retirada");
  expect(w.text()).toContain("Para hoje");
  expect(modeButton("Encomendas").attributes("aria-pressed")).toBe("true");
  expect(modeButton("Encomendas").classes()).toContain("bg-primary");
  expect(modeButton("Balcão").classes()).not.toContain("bg-primary");
  w.unmount();
});
