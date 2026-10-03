import { afterEach, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";
import PosPreorderRescheduleDialog from "~/components/PosPreorderRescheduleDialog.vue";
import PosSchedulePicker from "~/components/PosSchedulePicker.vue";
import type { ScheduleWindow } from "~/presentation/schedule";

// Reagendar usa a "Escolha rápida de dia" do kit (Tipo 1), com os dias que o
// servidor diz combináveis: dia fechado aparece apagado com o motivo.
const BASE = {
  // 12/09/2026 é sábado; domingo 13 fechado. A última data ofertada (15/09) é o
  // limite de dias da casa.
  today: "2026-09-12",
  available_dates: ["2026-09-12", "2026-09-14", "2026-09-15"],
  windows: [] as ScheduleWindow[],
  bottleneck_name: "",
  ready_at: "",
};
let response = { ...BASE };
registerEndpoint("/api/v1/backstage/pos/schedule/", () => response);

afterEach(() => {
  document.body.innerHTML = "";
  response = { ...BASE };
});

const day = (key: string) => document.querySelector<HTMLButtonElement>(`[data-day-option="${key}"]`);

it("escolher a próxima data marca o dia novo e libera o confirmar", async () => {
  const w = await mountSuspended(PosPreorderRescheduleDialog, {
    props: { open: false, customerName: "Ana", currentDate: "2026-09-12", currentSlot: "", skus: ["CROISSANT"] },
  });
  await w.setProps({ open: true });
  await vi.waitFor(() => expect(day("today")).not.toBeNull());

  expect(day("today")?.getAttribute("aria-checked")).toBe("true");
  expect(day("tomorrow")?.disabled).toBe(true);
  expect(day("tomorrow")?.textContent).toContain("fechado");

  day("next")?.click();
  await flushPromises();
  await w.vm.$nextTick();
  expect(day("next")?.getAttribute("aria-checked")).toBe("true");
  const confirm = document.querySelector<HTMLButtonElement>("[data-preorder-reschedule-confirm]");
  expect(confirm?.disabled).toBe(false);
  w.unmount();
});

it("o reagendar respeita o limite de dias da casa, como a venda", async () => {
  const w = await mountSuspended(PosPreorderRescheduleDialog, {
    props: { open: false, customerName: "Ana", currentDate: "2026-09-12", currentSlot: "", skus: ["CROISSANT"] },
  });
  await w.setProps({ open: true });
  await vi.waitFor(() => expect(day("other")).not.toBeNull());

  day("other")?.click();
  await vi.waitFor(() => expect(document.querySelector("[data-day-other-input]")).not.toBeNull());
  expect(document.querySelector("[data-day-other-input]")?.getAttribute("max")).toBe("2026-09-15");
  w.unmount();
});

it("avisa quando o horário combinado ficou impossível para estes itens", async () => {
  response = {
    ...BASE,
    windows: [
      { ref: "slot-09", label: "A partir das 9h", enabled: false, reason: "A baguete sai às 12:00." },
      { ref: "slot-12", label: "A partir das 12h", enabled: true },
    ],
  };
  const w = await mountSuspended(PosPreorderRescheduleDialog, {
    props: { open: false, customerName: "Ana", currentDate: "2026-09-12", currentSlot: "slot-09", skus: ["BAGUETE"] },
  });
  await w.setProps({ open: true });
  await vi.waitFor(() => expect(document.querySelector("[data-schedule-conflict]")).not.toBeNull());
  expect(document.querySelector("[data-schedule-conflict]")?.textContent).toContain("A baguete sai às 12:00.");

  // Escolher uma janela que cabe tira o aviso.
  document.querySelector<HTMLButtonElement>('[data-schedule-slot="slot-12"]')?.click();
  await w.vm.$nextTick();
  expect(document.querySelector("[data-schedule-conflict]")).toBeNull();
  w.unmount();
});

it("o reagendar usa o mesmo seletor de dia e horário da venda", async () => {
  const w = await mountSuspended(PosPreorderRescheduleDialog, {
    props: { open: true, customerName: "Ana", currentDate: "2026-09-12", currentSlot: "", skus: ["CROISSANT"] },
  });
  expect(w.findComponent(PosSchedulePicker).exists()).toBe(true);
  w.unmount();
});
