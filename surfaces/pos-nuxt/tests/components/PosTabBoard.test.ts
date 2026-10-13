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
  // Só a comanda inteira pronta veste "Tudo pronto"; a outra, enviada e não pronta, segue "Não pago".
  expect(badges).toHaveLength(1);
  expect(w.find('[data-tab-badge="unpaid"]').attributes("aria-label")).toBe("Não pago");
  const badge = badges[0]!;
  expect(badge.find("[data-tab-badge-label]").text()).toBe("Tudo pronto");
  expect(badge.attributes("aria-label")).toBe("Tudo pronto");
  expect(badge.attributes("title")).toBe("Tudo pronto: a cozinha terminou tudo desta comanda");
  // Selo é soft (D1, o default do tema do kit), nunca o verde cheio.
  expect(badge.classes().join(" ")).toContain("bg-success/10");
  expect(badge.classes()).not.toContain("bg-success");
  expect(w.text()).not.toContain("Pronta");
  w.unmount();
});

it("todo estado do cartão sai no MESMO selo: NuxtBadge soft, um tamanho, só cor/ícone/texto mudam (D1/D5/D11)", async () => {
  const w = await board([
    tab({ ref: "12", session_key: "sk-12", state: "in_use", item_count: 2, fired: true, kitchen_ready: true }),
    tab({ ref: "13", session_key: "sk-13", state: "in_use", item_count: 1, fired: true }),
    tab({ ref: "14", session_key: "sk-14", state: "in_use", item_count: 1 }),
    tab({ ref: "15", status_label: "Livre" }),
    tab({ ref: "16", session_key: "sk-16", state: "in_use", status_label: "Em uso" }),
  ]);
  const cards = w.findAll("[data-tab-badge]");
  expect(cards.map((b) => b.attributes("data-tab-badge")).sort()).toEqual(["pending", "ready", "status", "status", "unpaid"]);
  // Cada cartão tem UM selo, e nenhuma pílula copiada à mão sobrou no cabeçalho.
  expect(w.findAll("button .rounded-full:not([data-tab-badge])")).toHaveLength(0);
  // A forma é a mesma em todos: tirando as classes de cor, o conjunto de classes bate.
  const isColor = (c: string) => /^(bg|text)-/.test(c) && c !== "text-xs";
  const shape = (classes: string[]) => [...new Set(classes.filter((c) => !isColor(c)))].sort().join(" ");
  const shapes = new Set(cards.map((b) => shape(b.classes())));
  expect(shapes.size).toBe(1);
  // Soft (o default do tema): fundo /10, nunca o cheio; e tamanho md (text-xs), o mesmo do resto do cartão.
  for (const b of cards) {
    expect(b.classes()).not.toContain("bg-success");
    expect(b.classes()).not.toContain("bg-warning");
    expect(b.classes()).toContain("text-xs");
    // Não se corta: o texto é o mesmo do aria, e o ícone fica quando o texto sai.
    expect(b.find("[data-tab-badge-label]").text()).toBe(b.attributes("aria-label"));
    expect(b.attributes("title")?.startsWith(`${b.attributes("aria-label")}: `)).toBe(true);
    expect(b.find("[data-tab-badge-label]").classes()).toEqual(["hidden", "@[9rem]:inline"]);
  }
  // Livre é neutro e discreto: a mesma cor do "A enviar", nada de verde ou âmbar.
  const free = w.findAll('[data-tab-badge="status"]').find((b) => b.text() === "Livre")!;
  expect(free.attributes("title")).toBe("Livre: comanda disponível");
  expect(free.classes().join(" ")).not.toMatch(/success|warning/);
  w.unmount();
});
