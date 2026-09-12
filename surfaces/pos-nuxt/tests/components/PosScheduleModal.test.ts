import { afterEach, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import PosScheduleModal from "~/components/PosScheduleModal.vue";

afterEach(() => { document.body.innerHTML = ""; });
it("encomenda exige data explícita e Hoje grava a data da loja", async () => {
  const w = await mountSuspended(PosScheduleModal, { props: {
    salesMode: "order", open: true, today: "2026-09-12", deliveryDate: "", deliveryDateEffective: "2026-09-12",
    deliveryTimeSlot: "", fulfillmentType: "pickup", availableDates: [], windows: [], bottleneckName: "", readyAt: "", maxDate: "2026-10-12", pending: false,
  } });
  const buttons = () => [...document.querySelectorAll<HTMLButtonElement>('button')];
  expect(buttons().find((b) => b.textContent?.trim() === "Concluir")?.disabled).toBe(true);
  expect(document.querySelector<HTMLInputElement>('input[type="date"]')?.value).toBe("");
  buttons().find((b) => b.textContent?.trim() === "Hoje")?.click();
  expect(w.emitted("update:deliveryDate")?.at(-1)).toEqual(["2026-09-12"]);
  await w.setProps({ deliveryDate: "2026-09-12" });
  expect(buttons().find((b) => b.textContent?.trim() === "Concluir")?.disabled).toBe(false);
  w.unmount();
});
