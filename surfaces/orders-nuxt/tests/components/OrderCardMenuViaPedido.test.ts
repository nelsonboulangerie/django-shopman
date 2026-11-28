// A Via Pedido no ⋯ do pedido do Gestor (P2-19 do mapa de cenários): o cartão e a
// linha da Grade dividem este menu, então o gesto aparece nos dois.
import { computed } from "vue";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import {
  createOrderTicketPrinter,
  ORDER_TICKET_PRINTER,
} from "../../app/composables/useOrderTicketPrint";
import OrderCardMenu from "../../app/components/OrderCardMenu.vue";
import type { OrderCardProjection, StationDeviceAgent } from "../../app/types/orders";

const env = installNuxtGlobals();
const AGENT: StationDeviceAgent = { can_print: true, agent_url: "http://127.0.0.1:9123", token: "t", reason: "" };

describe("OrderCardMenu: a Via Pedido no ⋯ do pedido", () => {
  const card = { ref: "WEB-6", actions: [], kitchen: null, volumes: 0, items_count: 1 } as unknown as OrderCardProjection;
  const stubs = { Icon: true, NuxtLink: { template: "<a><slot /></a>" } };

  beforeEach(() => {
    env.reset();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) }));
  });

  it("o ⋯ oferece Imprimir Via Pedido e o toque imprime", async () => {
    env.fetchMock.mockResolvedValue({ payload_b64: "QQ==", title: "filipeta:WEB-6", reprint: false });
    const printer = createOrderTicketPrinter(computed(() => AGENT));
    const w = mount(OrderCardMenu, {
      props: { card },
      global: { stubs, provide: { [ORDER_TICKET_PRINTER as symbol]: printer } },
    });
    await w.get("[data-card-menu]").trigger("click");
    const item = w.get("[data-card-order-ticket]");
    expect(item.attributes("aria-label")).toBe("Imprimir Via Pedido");
    await item.trigger("click");
    await vi.waitFor(() =>
      expect(env.fetchMock).toHaveBeenCalledWith("/api/v1/backstage/orders/WEB-6/ticket-escpos/", { method: "POST" }),
    );
  });

  it("quem só expede não vê o gesto (a rota é de quem gerencia)", async () => {
    const printer = createOrderTicketPrinter(computed(() => AGENT));
    const w = mount(OrderCardMenu, {
      props: { card, canOpen: false },
      global: { stubs, provide: { [ORDER_TICKET_PRINTER as symbol]: printer } },
    });
    await w.get("[data-card-menu]").trigger("click");
    expect(w.find("[data-card-order-ticket]").exists()).toBe(false);
  });
});
