import { afterEach, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";
import PosPreorderRescheduleDialog from "~/components/PosPreorderRescheduleDialog.vue";

// Reagendar usa a "Escolha rápida de dia" do kit (Tipo 1), com os dias que o
// servidor diz combináveis: dia fechado aparece apagado com o motivo.
registerEndpoint("/api/v1/backstage/pos/schedule/", () => ({
  // 12/09/2026 é sábado; domingo 13 fechado.
  today: "2026-09-12",
  available_dates: ["2026-09-12", "2026-09-14", "2026-09-15"],
  windows: [],
  bottleneck_name: "",
  ready_at: "",
}));

afterEach(() => { document.body.innerHTML = ""; });

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
