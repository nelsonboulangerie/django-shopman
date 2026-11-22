// A taxa de entrega na tela de venda (#2402): fora do pagamento a review não roda,
// e o Recebimento dizia "A taxa deste endereço é calculada no pagamento" com o
// cliente no telefone perguntando quanto fica. Agora a tela pergunta a taxa à porta
// `pos/delivery-fee/` (o mesmo motor da review) assim que há endereço de entrega.
import { mockNuxtImport } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";

import { makeSale } from "./_posSaleHarness";

const { dollarFetch } = vi.hoisted(() => ({ dollarFetch: vi.fn() }));
// `$fetch` é auto-import do Nuxt: stub de global não o alcança.
mockNuxtImport("$fetch", () => dollarFetch);

vi.mock("vue-sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() } }));

const ZONA = { delivery_fee_q: 800, delivery_fee_source: "zone", delivery_distance_km: null, delivery_fee_waiver: null };

type Harness = ReturnType<typeof makeSale>;
let instances: Harness[] = [];

function quoteCalls() {
  return dollarFetch.mock.calls.filter((call) => String(call[0]).includes("/pos/delivery-fee/"));
}

function deliverySale() {
  const h = makeSale();
  instances.push(h);
  h.sale.cart.fulfillmentType = "delivery";
  h.sale.cart.customerRef = "CUST-A";
  return h;
}

async function settle() {
  await nextTick();
  await vi.advanceTimersByTimeAsync(400);
  await nextTick();
}

beforeEach(() => {
  vi.useFakeTimers();
  dollarFetch.mockReset();
});

afterEach(() => {
  for (const h of instances.splice(0)) h.handles.dispose();
  vi.useRealTimers();
});

describe("usePosSale: a taxa de entrega na tela de venda", () => {
  it("sem endereço a tela não pergunta, e diz que falta o endereço", async () => {
    const { sale } = deliverySale();
    await settle();

    expect(quoteCalls()).toHaveLength(0);
    expect(sale.deliveryFeeStatus.value).toBe("at_payment");
  });

  it("com endereço, pergunta à porta da taxa e mostra o número da loja", async () => {
    dollarFetch.mockResolvedValue(ZONA);
    const { sale } = deliverySale();
    sale.cart.deliveryAddress = "Rua Pará, 86";
    sale.cart.deliveryNeighborhood = "Centro";
    await nextTick();
    expect(sale.deliveryFeeStatus.value).toBe("calculating");

    await settle();

    expect(quoteCalls()).toHaveLength(1);
    const [, options] = quoteCalls()[0]!;
    expect(options.method).toBe("POST");
    expect(options.body).toMatchObject({ customer_ref: "CUST-A" });
    expect(sale.deliveryFeeStatus.value).toBe("resolved");
    expect(sale.deliveryFeeQ.value).toBe(800);
    expect(sale.deliveryFeeSource.value).toBe("zone");
  });

  it("outro endereço é outra pergunta; a resposta velha não vale para ele", async () => {
    dollarFetch.mockResolvedValue(ZONA);
    const { sale } = deliverySale();
    sale.cart.deliveryAddress = "Rua Pará, 86";
    sale.cart.deliveryNeighborhood = "Centro";
    await settle();
    expect(sale.deliveryFeeQ.value).toBe(800);

    dollarFetch.mockResolvedValue({ ...ZONA, delivery_fee_q: 1200 });
    sale.cart.deliveryNeighborhood = "Gleba Palhano";
    await nextTick();
    // Até a porta responder para o endereço novo, a taxa do antigo não aparece.
    expect(sale.deliveryFeeStatus.value).toBe("calculating");
    await settle();

    expect(quoteCalls()).toHaveLength(2);
    expect(sale.deliveryFeeQ.value).toBe(1200);
  });

  it("a porta falhou: a tela diz isso, não fica calculando para sempre", async () => {
    dollarFetch.mockRejectedValue({ status: 502 });
    const { sale } = deliverySale();
    sale.cart.deliveryAddress = "Rua Pará, 86";
    await settle();

    expect(sale.deliveryFeeStatus.value).toBe("failed");
  });

  it("retirada não pergunta taxa nenhuma", async () => {
    const { sale } = deliverySale();
    sale.cart.fulfillmentType = "pickup";
    sale.cart.deliveryAddress = "Rua Pará, 86";
    await settle();

    expect(quoteCalls()).toHaveLength(0);
  });
});
