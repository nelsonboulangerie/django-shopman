import { expect, it } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import PosTabBoard from "~/components/PosTabBoard.vue";
import type { POSTabProjection } from "~/types/pos";

function tab(overrides: Partial<POSTabProjection> & { ref: string }): POSTabProjection {
  return {
    display_ref: overrides.ref,
    session_key: "",
    state: "empty",
    status_label: "",
    status_class: "",
    customer_name: "",
    customer_phone: "",
    item_count: 0,
    line_count: 0,
    total_display: "",
    last_touched_display: "",
    items_preview: "",
    ...overrides,
  };
}

const board = (tabs: POSTabProjection[]) => mountSuspended(PosTabBoard, {
  props: {
    tabs, selectedTabRef: "", hasDraft: false, busy: false, modelValue: "",
    maxLength: 20, placeholder: "", disallowedChars: [], zeroPadTo: 0,
  },
});

it("comanda que a cozinha terminou: selo soft \"Tudo pronto\", com o nome inteiro na dica e no aria (dono, 13/10/2026)", async () => {
  const w = await board([
    tab({ ref: "12", session_key: "sk-12", state: "in_use", item_count: 2, fired: true, kitchen_ready: true }),
    tab({ ref: "13", session_key: "sk-13", state: "in_use", item_count: 1, fired: true }),
  ]);
  const badges = w.findAll("[data-tab-kitchen-ready]");
  // Só a comanda inteira pronta veste o selo; a outra, disparada e não pronta, segue "Não pago".
  expect(badges).toHaveLength(1);
  const badge = badges[0]!;
  expect(badge.find("[data-tab-kitchen-ready-label]").text()).toBe("Tudo pronto");
  expect(badge.attributes("aria-label")).toBe("Tudo pronto");
  expect(badge.attributes("title")).toBe("Tudo pronto: a cozinha terminou tudo desta comanda");
  // Selo é soft (D1, o default do tema do kit), nunca o verde cheio.
  expect(badge.classes().join(" ")).toContain("bg-success/10");
  expect(badge.classes()).not.toContain("bg-success");
  expect(w.text()).not.toContain("Pronta");
  w.unmount();
});
