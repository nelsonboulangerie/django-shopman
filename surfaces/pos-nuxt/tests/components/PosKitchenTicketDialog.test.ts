import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { enableAutoUnmount, flushPromises } from "@vue/test-utils";
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";

import PosCartPanel from "~/components/PosCartPanel.vue";
import PosKitchenTicketDialog from "~/components/PosKitchenTicketDialog.vue";
import type { POSCartItem, POSKitchenTicket } from "~/types/pos";

// O card da cozinha no PDV: o toque na linha disparada mostra estação, itens,
// disparo e estado — e o "Pronto" quando a estação não tem tela.
const { fetchMock, toast } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));
mockNuxtImport("$fetch", () => fetchMock);
vi.mock("vue-sonner", async (importOriginal) => ({ ...(await importOriginal<object>()), toast }));

enableAutoUnmount(afterEach);

function ticket(over: Partial<POSKitchenTicket> = {}): POSKitchenTicket {
  return {
    pk: 77,
    station_name: "Lanches",
    prints: true,
    status: "pending",
    status_label: "Na fila",
    fired_at_display: "10:40",
    paper_label: "impresso às 10:42",
    paper_failed: false,
    items: [{ name: "X-Burguer", qty: 2, notes: "sem cebola" }],
    can_mark_ready: true,
    ...over,
  };
}

describe("PosKitchenTicketDialog", () => {
  beforeEach(() => {
    fetchMock.mockReset().mockResolvedValue({ ticket: { completed_now: true, message: "Lanches pronto · Ana · #1234" } });
    Object.values(toast).forEach((fn) => fn.mockReset());
  });

  it("mostra a estação, o disparo, o papel e os itens", async () => {
    const wrapper = await mountSuspended(PosKitchenTicketDialog, {
      props: { open: true, lineName: "X-Burguer", tickets: [ticket()] },
      attachTo: document.body,
    });
    const text = document.body.textContent || "";
    expect(text).toContain("Lanches");
    expect(text).toContain("enviado às 10:40");
    expect(text).toContain("impresso às 10:42");
    expect(text).toContain("2× X-Burguer");
    expect(text).toContain("sem cebola");
    wrapper.unmount();
  });

  it("Pronto na estação sem tela chama a ação do servidor e avisa", async () => {
    const wrapper = await mountSuspended(PosKitchenTicketDialog, {
      props: { open: true, lineName: "X-Burguer", tickets: [ticket()] },
      attachTo: document.body,
    });
    const button = [...document.body.querySelectorAll("button")].find((b) => b.textContent?.includes("Pronto"));
    expect(button).toBeTruthy();
    button!.click();
    await flushPromises();
    const [path, opts] = fetchMock.mock.calls[0]!;
    expect(String(path)).toContain("/api/v1/backstage/kds/printed-tickets/77/done/");
    expect(opts.method).toBe("POST");
    expect(toast.success).toHaveBeenCalledWith("Lanches pronto · Ana · #1234");
    wrapper.unmount();
  });

  it("estação de tela não tem Pronto no balcão", async () => {
    const wrapper = await mountSuspended(PosKitchenTicketDialog, {
      props: {
        open: true,
        lineName: "Café",
        tickets: [ticket({ station_name: "Cafés", prints: false, can_mark_ready: false, status_label: "Em preparo", paper_label: "" })],
      },
      attachTo: document.body,
    });
    const text = document.body.textContent || "";
    expect(text).toContain("Cafés tem tela: o pronto é dado lá.");
    expect([...document.body.querySelectorAll("button")].some((b) => b.textContent?.trim() === "Pronto")).toBe(false);
    wrapper.unmount();
  });
});

describe("PosCartPanel — a linha disparada abre o card da cozinha", () => {
  it("só a linha que foi para a cozinha tem o botão", async () => {
    const items: POSCartItem[] = [
      { line_id: "L1", sku: "XB", name: "X-Burguer", price_q: 2500, qty: 1, notes: "", fired: true, kitchen_status: "pending", kitchen_tickets: [ticket()] },
      { line_id: "L2", sku: "PAO", name: "Pão", price_q: 500, qty: 1, notes: "" },
    ];
    const wrapper = await mountSuspended(PosCartPanel, {
      props: {
        items,
        requiresTab: false,
        hasOpenTab: true,
        loading: false,
        saving: false,
        fireAction: { ref: "fire_tab", present: true, label: "Enviar à cozinha", priority: "primary", enabled: true, reason: "", href: "/x" },
        unfireAction: { ref: "unfire_tab", present: true, label: "Cancelar envio", priority: "secondary", enabled: true, reason: "", href: "/x" },
        firing: false,
      },
    });
    const buttons = wrapper.findAll("[data-testid=kitchen-card-open]");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]!.attributes("aria-label")).toBe("Ver X-Burguer na cozinha");
  });
});
