import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it, vi } from "vitest";

import PosRecentSales from "~/components/PosRecentSales.vue";

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
mockNuxtImport("$fetch", () => fetchMock);
// `importOriginal` mantém o `Toaster` (o shell o monta); só o `toast` é espionado.
vi.mock("vue-sonner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("vue-sonner")>()),
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

function sale(overrides: Record<string, unknown> = {}) {
  return {
    order_ref: "PDV-042",
    status: "confirmed",
    created_at_display: "10:12",
    total_display: "42,00",
    payment_label: "Pix",
    customer_name: "",
    fiscal_status: "pending",
    fiscal_label: "Rótulo do servidor",
    fiscal_links: [],
    nfce_number: "",
    email_sent: false,
    receipt_email: "",
    can_print_danfe: false,
    can_resend_email: false,
    can_requeue_fiscal: false,
    can_cancel: false,
    ...overrides,
  };
}

async function montar(sales: Record<string, unknown>[]) {
  fetchMock.mockResolvedValue({ sales });
  // A lista carrega ao ABRIR (watcher de `open`), como na tela.
  const w = await mountSuspended(PosRecentSales, { props: { open: false, pos: null } });
  await w.setProps({ open: true });
  await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
  await vi.waitFor(() => expect(document.body.querySelectorAll("[data-fiscal-chip]").length).toBe(sales.length));
  return w;
}

/**
 * O chip fiscal da lista fala o MESMO estado da tela de resultado quando o
 * servidor manda `fiscal_state`; sem ele, o rótulo pronto de sempre.
 */
describe("PosRecentSales — o chip fiscal segue `fiscal_state` quando existe", () => {
  const chips = () => Array.from(document.body.querySelectorAll("[data-fiscal-chip]")).map((el) => el.textContent?.trim());

  it("os cinco estados viram o rótulo canônico", async () => {
    const w = await montar([
      sale({ order_ref: "A", fiscal_state: "authorized" }),
      sale({ order_ref: "B", fiscal_state: "queued" }),
      sale({ order_ref: "C", fiscal_state: "awaiting_payment" }),
      sale({ order_ref: "D", fiscal_state: "failed" }),
      sale({ order_ref: "E", fiscal_state: "not_expected" }),
    ]);
    expect(chips()).toEqual(["NFC-e autorizada", "NFC-e na fila", "NFC-e aguarda o pagamento", "NFC-e falhou", "Sem NFC-e"]);
    w.unmount();
  });

  it("sem `fiscal_state`, vale o rótulo do servidor", async () => {
    const w = await montar([sale()]);
    expect(chips()).toEqual(["Rótulo do servidor"]);
    w.unmount();
  });
});
