import { setResponseStatus } from "h3";
import { mockNuxtImport, mountSuspended, registerEndpoint } from "@nuxt/test-utils/runtime";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computed, reactive, ref } from "vue";

import DetailPage from "~/pages/preorders/[ref].vue";
import type { PreorderCard, PreorderDetail, PreorderSwapResponse } from "~/types/preorders";

import { makeProjection } from "../composables/_posSaleHarness";

// A troca do item que falta (#2765): o "Trocar por <produto>" do diálogo
// "Resolver" do Gestor abre o detalhe em `?swap=<sku>`. O endereço leva só a
// intenção; as alternativas vêm do servidor, a troca grava pela edição.

const call = vi.fn();
mockNuxtImport("usePosTerminal", () => async () => ({
  pos: computed(() => makeProjection({ has_open_cash_session: true })),
  pending: ref(false),
  refresh: vi.fn().mockResolvedValue(undefined),
}));
mockNuxtImport("useOperatorLock", () => () => ({ operator: ref({ name: "Ana" }), lock: vi.fn() }));
mockNuxtImport("usePosAction", () => () => ({ call }));
mockNuxtImport("usePosOrderTickets", () => () => ({
  printOne: vi.fn().mockResolvedValue(true),
  printBatch: vi.fn().mockResolvedValue(true),
  printing: ref(false),
  printingRef: ref(""),
  hasPrinter: ref(true),
  printerUnavailableReason: ref(""),
}));
mockNuxtImport("navigateTo", () => vi.fn().mockResolvedValue(undefined));
const route = reactive({ params: { ref: "NB-7" }, query: {} as Record<string, unknown>, path: "/preorders/NB-7" });
// O `mountSuspended` navega para "/" ao montar: só a troca de query da tela muda a rota.
const replace = vi.fn((to: string | { query: Record<string, unknown> }) => {
  if (typeof to !== "string") route.query = { ...to.query };
  return Promise.resolve();
});
mockNuxtImport("useRoute", () => () => route);
mockNuxtImport("useRouter", () => () => ({ replace, afterEach: vi.fn(), beforeResolve: vi.fn() }));

function card(): PreorderCard {
  return {
    ref: "NB-7", channel_display_id: "", customer_name: "Ana Souza", channel_ref: "web",
    channel_label: "Loja online", fulfillment_type: "pickup", fulfillment_label: "Retirada",
    commitment_date: "2026-09-27", commitment_date_display: "amanhã", window_label: "9h às 10h",
    window_start: "09:00", status: "accepted", situation: "to_pay", situation_label: "A pagar",
    payment_state: "to_receive",
    total_q: 6200, total_display: "R$ 62,00", balance_q: 6200, balance_display: "R$ 62,00",
    items_summary: "4x Baguete", items_count: 2, ticket_printed: false,
  };
}

let detail: PreorderDetail;
let swap: PreorderSwapResponse;
let swapFailure = false;
const swapRead = vi.fn();

registerEndpoint("/api/v1/backstage/pos/preorders/NB-7/", () => ({
  order: detail, payment_check_due: false, generated_at: "2026-09-26T12:00:00Z", contract_version: 1,
}));
registerEndpoint("/api/v1/backstage/pos/preorders/NB-7/swap/", (event) => {
  swapRead(event.path);
  if (swapFailure) {
    setResponseStatus(event, 503);
    return { detail: "Fora do ar." };
  }
  return swap;
});

const mounted: VueWrapper[] = [];
async function mount() {
  clearNuxtData();
  const wrapper = await mountSuspended(DetailPage as never, {
    global: { stubs: { PosFunctionRail: true, RailToggle: true, MoreBelow: true } },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  await settle();
  return wrapper;
}
async function settle() {
  await flushPromises();
  await flushPromises();
  await flushPromises();
}
const body = () => document.body;

function fendu(partial = {}) {
  return {
    sku: "FENDU", name: "Fendu", label: "Trocar por Fendu", available_display: "10 livres para amanhã",
    qty_label: "4x Fendu", enabled: true, reason: "",
    total_before_q: 6200, total_after_q: 6600, difference_q: 400,
    total_before_display: "R$ 62,00", total_after_display: "R$ 66,00", difference_display: "R$ 4,00 a mais",
    money: "O novo total é R$ 66,00, a pagar na retirada.",
    requires_manager_approval: false, refund_q: 0, ...partial,
  };
}

beforeEach(() => {
  route.query = {};
  swapFailure = false;
  swapRead.mockClear();
  replace.mockClear();
  call.mockReset();
  call.mockResolvedValue({ ok: true, outcome: "applied", changed: true });
  detail = {
    ref: "NB-7", status: "accepted", status_label: "Aceito", context: "pos", actions: [],
    channel_ref: "web", channel_name: "Loja online", channel_icon: "language", total_display: "R$ 62,00",
    customer_name: "Ana Souza", customer_ref: "C-1", customer_phone: "", customer_phone_uri: "",
    customer_whatsapp_url: "", customer_email: "", customer_relay_phone: "", customer_relay_code: "",
    customer_relay_expires_at: "", fulfillment_type: "pickup", fulfillment_label: "Retirada",
    schedule_label: "Amanhã · 9h às 10h", delivery_address: "", delivery_instructions: "",
    payment_method_label: "Dinheiro na retirada", payment_status_label: "Pendente", payment_link_notice: "",
    test_order_notice: "", is_gift: false, gift_recipient_name: "", gift_recipient_phone: "", gift_message: "",
    gift_hide_values: false, customer_profile: null, fiscal_status_label: "", fiscal_links: [],
    items: [
      { sku: "BAGUETE", name: "Baguete", qty: "4", unit_price_display: "R$ 11,00", total_display: "R$ 44,00" },
      { sku: "CAFE", name: "Café coado", qty: "2", unit_price_display: "R$ 9,00", total_display: "R$ 18,00" },
    ],
    customer_note: "", kitchen_note: "", timeline: [],
    counter: {
      card: card(), ticket_printed: false, revision: "rev-1", actor_id: 7,
      hand_over: {
        allowed: false, needs_payment: true, amount_q: 6200, amount_display: "R$ 62,00",
        suggested_method: "cash", block_reason: "", digital_charge_notice: "",
      },
      cancel: { allowed: true, requires_approval: false, block_reason: "" },
      reschedule: { allowed: true, block_reason: "", date: "2026-09-27", slot: "slot-09", skus: ["BAGUETE"], revision: "rev-schedule" },
      edit: { allowed: true, block_reason: "", cancel_and_redo: false, revision: "rev-edit" },
    },
    managers: [{ username: "gerente", name: "Gerente" }],
    cancel_reasons: [],
  } as unknown as PreorderDetail;
  swap = {
    order_ref: "NB-7", base_revision: "rev-edit-1", expected_actor_id: 7, refusal_code: "", refusal: "",
    items: [{
      sku: "BAGUETE", name: "Baguete", qty: "4", qty_label: "4x Baguete",
      fact: "Faltam 4x Baguete. O lote de amanhã foi cancelado.", searched: true, empty_phrase: "",
      options: [
        fendu(),
        fendu({
          sku: "CAMPAGNE", name: "Pain de Campagne", label: "Trocar por Pain de Campagne",
          available_display: "6 livres para amanhã", qty_label: "4x Pain de Campagne", difference_display: "R$ 30,80 a mais",
        }),
      ],
    }],
  };
});
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.body.innerHTML = "";
});

describe("Encomenda aberta pelo link da troca (#2765)", () => {
  it("sem swap, a página abre como sempre e não pergunta nada da troca", async () => {
    const wrapper = await mount();
    expect(wrapper.find("[data-order-detail]").exists()).toBe(true);
    expect(wrapper.find("[data-preorder-swap]").exists()).toBe(false);
    expect(swapRead).not.toHaveBeenCalled();
  });

  it("swap com SKU fora do pedido: o servidor ignora e a página abre como sempre, sem aviso", async () => {
    route.query = { swap: "NAO-EXISTE" };
    swap.items = [];
    const wrapper = await mount();
    expect(swapRead).toHaveBeenCalledTimes(1);
    expect(swapRead.mock.calls[0]![0]).toContain("sku=NAO-EXISTE");
    expect(wrapper.find("[data-preorder-swap]").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Não deu para");
  });

  it("swap vazio ou só de lixo nem pergunta ao servidor", async () => {
    route.query = { swap: ["", "  "] };
    await mount();
    expect(swapRead).not.toHaveBeenCalled();
  });

  it("com swap, mostra o item a trocar e uma alternativa por linha, com a fornada e a diferença", async () => {
    route.query = { swap: ["BAGUETE", "BAGUETE"] };
    const wrapper = await mount();

    // A URL leva só a intenção: o SKU vai ao servidor uma vez, nada mais.
    expect(swapRead).toHaveBeenCalledTimes(1);
    expect(swapRead.mock.calls[0]![0]).toMatch(/\/swap\/\?sku=BAGUETE$/);
    const block = wrapper.get("[data-preorder-swap-item='BAGUETE']");
    expect(block.attributes("data-focus-target")).toBe("swap:BAGUETE");
    expect(block.get("[data-preorder-swap-title]").text()).toBe("Trocar 4x Baguete");
    expect(block.get("[data-preorder-swap-fact]").text()).toBe("Faltam 4x Baguete. O lote de amanhã foi cancelado.");
    const rows = block.findAll("[data-preorder-swap-option]");
    expect(rows.map((row) => row.attributes("data-preorder-swap-option"))).toEqual(["FENDU", "CAMPAGNE"]);
    expect(rows[0]!.text()).toContain("Trocar por Fendu");
    expect(rows[0]!.text()).toContain("10 livres para amanhã");
    expect(rows[0]!.get("[data-preorder-swap-difference]").text()).toBe("R$ 4,00 a mais");
  });

  it("um toque confere a troca e confirma pela edição; o item trocado sai do endereço", async () => {
    route.query = { swap: "BAGUETE", back: "/preorders?mode=week" };
    const wrapper = await mount();
    await wrapper.get("[data-preorder-swap-option='FENDU']").trigger("click");
    await settle();

    const dialog = body().querySelector("[data-preorder-swap-dialog]")!;
    expect(dialog.querySelector("[data-preorder-swap-out]")!.textContent).toBe("4x Baguete");
    expect(dialog.querySelector("[data-preorder-swap-in]")!.textContent).toBe("4x Fendu");
    expect(dialog.querySelector("[data-preorder-swap-before]")!.textContent).toBe("R$ 62,00");
    expect(dialog.querySelector("[data-preorder-swap-after]")!.textContent).toBe("R$ 66,00");
    expect(dialog.querySelector("[data-preorder-swap-money]")!.textContent).toBe("O novo total é R$ 66,00, a pagar na retirada.");
    const confirm = body().querySelector<HTMLButtonElement>("[data-preorder-swap-confirm]")!;
    expect(confirm.textContent).toContain("Trocar por Fendu");
    confirm.click();
    await settle();

    const [path, options] = call.mock.calls[0]!;
    expect(path).toBe("/api/v1/backstage/pos/preorders/NB-7/swap/");
    expect(options.body).toMatchObject({ sku: "BAGUETE", offer: "FENDU", base_revision: "rev-edit-1", expected_actor_id: 7 });
    expect(options.body.idempotency_key).toBeTruthy();
    // Nome, preço e quantidade nunca saem da tela: o servidor relê e calcula.
    expect(Object.keys(options.body).sort()).toEqual(["base_revision", "expected_actor_id", "idempotency_key", "offer", "sku"]);
    expect(replace).toHaveBeenLastCalledWith({ query: { back: "/preorders?mode=week" } });
    expect(body().querySelector("[data-preorder-swap-dialog]")).toBeNull();
  });

  it("a alternativa que deixou de caber: recusa, relê a lista e não fecha o endereço", async () => {
    route.query = { swap: "BAGUETE" };
    call.mockRejectedValueOnce(Object.assign(new Error("400"), {
      statusCode: 400,
      data: { detail: "Este produto não está mais livre para a data da encomenda. Nada mudou: escolha outra alternativa.", code: "swap_offer_gone" },
    }));
    const wrapper = await mount();
    await wrapper.get("[data-preorder-swap-option='FENDU']").trigger("click");
    await settle();
    swap.items[0]!.options = swap.items[0]!.options.slice(1);
    body().querySelector<HTMLButtonElement>("[data-preorder-swap-confirm]")!.click();
    await settle();

    expect(replace.mock.calls.filter(([to]) => typeof to !== "string")).toEqual([]);
    expect(swapRead).toHaveBeenCalledTimes(2);
    expect(wrapper.findAll("[data-preorder-swap-option]").map((row) => row.attributes("data-preorder-swap-option"))).toEqual(["CAMPAGNE"]);
  });

  it("busca vazia diz que não há nada parecido e oferece o Reagendar", async () => {
    route.query = { swap: "BAGUETE" };
    swap.items[0]!.options = [];
    swap.items[0]!.empty_phrase = "Nenhum produto parecido livre para amanhã.";
    const wrapper = await mount();
    const empty = wrapper.get("[data-preorder-swap-empty]");
    expect(empty.text()).toContain("Nenhum produto parecido livre para amanhã.");
    expect(empty.get("[data-preorder-swap-reschedule]").text()).toBe("Reagendar");
  });

  it("busca fora do ar não afirma que não há: o aviso do topo traz o Procurar de novo", async () => {
    route.query = { swap: "BAGUETE" };
    swap.items[0]!.options = [];
    swap.items[0]!.searched = false;
    const wrapper = await mount();
    expect(wrapper.find("[data-preorder-swap-empty]").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Nenhum produto parecido");
    expect(wrapper.text()).toContain("Não deu para procurar agora o que trocar por Baguete.");
    const retry = wrapper.findAll("button").find((button) => button.text() === "Procurar de novo");
    expect(retry).toBeTruthy();
    await retry!.trigger("click");
    await settle();
    expect(swapRead).toHaveBeenCalledTimes(2);
  });

  it("leitura da troca que falhou: aviso com Procurar de novo, e o detalhe segue de pé", async () => {
    route.query = { swap: "BAGUETE" };
    swapFailure = true;
    const wrapper = await mount();
    expect(wrapper.find("[data-order-detail]").exists()).toBe(true);
    expect(wrapper.text()).toContain("Não deu para ler as alternativas da troca.");
    expect(wrapper.findAll("button").some((button) => button.text() === "Procurar de novo")).toBe(true);
  });
});
