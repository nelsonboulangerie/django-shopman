// #2885: no celular (375 px), com um cadastro escolhido, o corpo do diálogo Cliente
// transbordava 90 px à direita. A linha do selo ("Cadastro existente · Nome", que não
// quebrava) e o "Remover cliente" lado a lado pediam 383 px num cartão de 277, e a
// coluna inteira do diálogo crescia junto. O cartão agora mede a si mesmo
// (`@container`): estreito, o botão desce para baixo do selo e o selo quebra linha.
//
// O jsdom não tem layout: aqui se trava a ESTRUTURA que faz caber. A geometria de
// verdade (scrollWidth, borda direita) é medida no navegador, em
// tests/geometry/customerModal.spec.ts (mock) e na jornada J12 (PDV ao vivo).
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it, vi } from "vitest";

import PosCustomerModal from "~/components/PosCustomerModal.vue";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn().mockResolvedValue({}) }));
mockNuxtImport("$fetch", () => fetchMock);

const MARIA = {
  ref: "MARIA",
  name: "Maria Santos",
  phone: "+5543991111111",
  email: "maria.santos.cliente@exemplo.com.br",
  tax_id: "",
  fiscal_prefs: {},
  notes: "",
  dietary_restrictions: "",
  birthday_display: "20/11",
  is_birthday_today: true,
  is_birthday_month: true,
  birthday_promo_label: "Parabéns! Desconto de aniversário",
  memory: { total_orders: 29, average_order_display: "", favorite_product: "", favorite_item: { sku: "CROISSANT" }, last_order_items: [] },
};

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;

afterEach(() => {
  mounted?.unmount();
  mounted = null;
  document.body.innerHTML = "";
});

async function mountWithMaria() {
  mounted = await mountSuspended(PosCustomerModal, {
    props: {
      open: true,
      customerName: MARIA.name,
      customerPhone: MARIA.phone,
      customerTaxId: "",
      customerEmail: MARIA.email,
      customerLookup: MARIA,
      searchResults: [],
      searchBusy: false,
      lookupBusy: false,
    },
    global: { stubs: { Icon: true } },
  });
}

const classes = (el: Element | null) => (el?.getAttribute("class") || "").split(/\s+/);

describe("PosCustomerModal no celular (#2885)", () => {
  it("o cartão do cadastro mede a si mesmo, e o cabeçalho empilha quando estreito", async () => {
    await mountWithMaria();
    const card = document.querySelector("[data-customer-state]");
    expect(classes(card)).toContain("@container");
    const header = document.querySelector("[data-customer-state-header]");
    // Estreito: coluna (selo em cima, "Remover cliente" embaixo). Largo: a linha de sempre.
    expect(classes(header)).toEqual(expect.arrayContaining(["flex", "flex-col", "@sm:flex-row", "@sm:justify-between"]));
    expect(header?.textContent).toContain("Remover cliente");
  });

  it("o selo e a linha de contato quebram linha no estreito, e só cortam no largo", async () => {
    await mountWithMaria();
    const badge = [...document.querySelectorAll("[data-customer-state] [role='status'] span")].find((el) => el.textContent?.includes("Cadastro existente · Maria Santos"));
    expect(badge).toBeTruthy();
    expect(classes(badge!)).not.toContain("truncate");
    expect(classes(badge!)).toContain("@sm:truncate");
    const contact = [...document.querySelectorAll("[data-customer-state] p")].find((el) => el.textContent?.includes(MARIA.email));
    expect(classes(contact!)).not.toContain("truncate");
    expect(classes(contact!)).toEqual(expect.arrayContaining(["wrap-anywhere", "@sm:truncate"]));
  });

  it("as colunas do corpo e do cartão não crescem pelo conteúdo mínimo (grid-cols-1, não `auto`)", async () => {
    await mountWithMaria();
    const card = document.querySelector("[data-customer-state]");
    expect(classes(card)).toContain("grid-cols-1");
    expect(classes(card?.parentElement ?? null)).toEqual(expect.arrayContaining(["grid", "grid-cols-1"]));
  });

  it("nada no corpo do diálogo pede largura fixa sem quebrar", async () => {
    await mountWithMaria();
    const card = document.querySelector("[data-customer-state]")!;
    const nowrap = [...card.querySelectorAll("*")].filter((el) => classes(el).some((c) => c === "truncate" || c === "whitespace-nowrap"));
    expect(nowrap.map((el) => el.outerHTML.slice(0, 80))).toEqual([]);
  });
});
