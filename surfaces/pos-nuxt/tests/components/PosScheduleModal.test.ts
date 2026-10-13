import { afterEach, expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import PosScheduleModal from "~/components/PosScheduleModal.vue";
import PosSchedulePicker from "~/components/PosSchedulePicker.vue";

afterEach(() => { document.body.innerHTML = ""; });

const props = {
  salesMode: "order" as const, open: true, today: "2026-09-12", deliveryDate: "", deliveryDateEffective: "2026-09-12",
  deliveryTimeSlot: "", fulfillmentType: "pickup" as const, availableDates: [], windows: [], bottleneckName: "", readyAt: "",
  maxDate: "2026-10-12", pending: false,
};
const buttons = () => [...document.querySelectorAll<HTMLButtonElement>("button")];
const day = (key: string) => document.querySelector<HTMLButtonElement>(`[data-day-option="${key}"]`);

it("encomenda exige data explícita e Hoje grava a data da loja", async () => {
  const w = await mountSuspended(PosScheduleModal, { props });
  expect(buttons().find((b) => b.textContent?.trim() === "Confirmar dia e horário")?.disabled).toBe(true);
  expect(document.querySelector('[data-day-picker] [aria-checked="true"]')).toBeNull();
  day("today")?.click();
  expect(w.emitted("update:deliveryDate")?.at(-1)).toEqual(["2026-09-12"]);
  await w.setProps({ deliveryDate: "2026-09-12" });
  expect(buttons().find((b) => b.textContent?.trim() === "Confirmar dia e horário")?.disabled).toBe(false);
  expect(day("today")?.getAttribute("aria-checked")).toBe("true");
  w.unmount();
});

it("o dia é a escolha rápida do kit: dia fechado apagado com o motivo, a próxima data nominada", async () => {
  // 12/09/2026 é sábado; domingo 13 fechado, segunda 14 aberta.
  const w = await mountSuspended(PosScheduleModal, {
    props: { ...props, availableDates: ["2026-09-12", "2026-09-14", "2026-09-15"] },
  });
  expect(day("tomorrow")?.disabled).toBe(true);
  expect(day("tomorrow")?.textContent).toContain("fechado");
  expect(day("next")?.textContent).toContain("Segunda-feira");
  day("next")?.click();
  expect(w.emitted("update:deliveryDate")?.at(-1)).toEqual(["2026-09-14"]);
  // Trocar o dia apaga a janela do dia anterior.
  expect(w.emitted("update:deliveryTimeSlot")?.at(-1)).toEqual([""]);
  w.unmount();
});

it("a venda usa o mesmo seletor de dia e horário do reagendar, com o limite de dias da casa", async () => {
  const w = await mountSuspended(PosScheduleModal, { props });
  const picker = w.findComponent(PosSchedulePicker);
  expect(picker.exists()).toBe(true);
  expect(picker.props("maxDate")).toBe("2026-10-12");
  w.unmount();
});

it("a venda avisa quando a janela escolhida ficou impossível", async () => {
  const w = await mountSuspended(PosScheduleModal, {
    props: {
      ...props,
      deliveryDate: "2026-09-12",
      deliveryTimeSlot: "slot-09",
      windows: [{ ref: "slot-09", label: "A partir das 9h", enabled: false, reason: "A baguete sai às 12:00." }],
    },
  });
  expect(document.querySelector("[data-schedule-conflict]")?.textContent).toContain("A baguete sai às 12:00.");
  w.unmount();
});

it("hoje oferece O quanto antes como primeira escolha, marcada sem janela", async () => {
  const w = await mountSuspended(PosScheduleModal, {
    props: {
      ...props,
      fulfillmentType: "delivery" as const,
      deliveryDate: "2026-09-12",
      windows: [{ ref: "16:00-16:30", label: "16:00 às 16:30", enabled: true, reason: "" }],
    },
  });
  const asap = document.querySelector<HTMLButtonElement>('[data-schedule-slot="asap"]');
  expect(asap?.textContent).toContain("O quanto antes");
  expect(asap?.getAttribute("aria-pressed")).toBe("true");
  // Sem "A combinar" no dia de hoje: vazio é o quanto antes.
  expect(buttons().some((b) => b.textContent?.trim() === "A combinar")).toBe(false);
  document.querySelector<HTMLButtonElement>('[data-schedule-slot="16:00-16:30"]')?.click();
  expect(w.emitted("update:deliveryTimeSlot")?.at(-1)).toEqual(["16:00-16:30"]);
  await w.setProps({ deliveryTimeSlot: "16:00-16:30" });
  expect(document.querySelector('[data-schedule-slot="asap"]')?.getAttribute("aria-pressed")).toBe("false");
  document.querySelector<HTMLButtonElement>('[data-schedule-slot="asap"]')?.click();
  expect(w.emitted("update:deliveryTimeSlot")?.at(-1)).toEqual([""]);
  w.unmount();
});

it("outro dia não tem O quanto antes: sem janela é a combinar", async () => {
  const w = await mountSuspended(PosScheduleModal, {
    props: {
      ...props,
      deliveryDate: "2026-09-14",
      deliveryTimeSlot: "slot-09",
      windows: [{ ref: "slot-09", label: "A partir das 9h", enabled: true, reason: "" }],
    },
  });
  expect(document.querySelector('[data-schedule-slot="asap"]')).toBeNull();
  expect(buttons().some((b) => b.textContent?.trim() === "A combinar")).toBe(true);
  w.unmount();
});
