import { computed, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  marketingOfferProblem,
  useMarketingOffers,
} from "~/composables/useMarketingOffers";

beforeEach(() => {
  vi.restoreAllMocks();
  Object.assign(globalThis, {
    computed,
    ref,
    marketingSessionOnError: vi.fn(),
    flagMarketingSessionError: vi.fn(),
    httpErrorMessage: vi.fn(() => "falhou"),
    useSonner: { success: vi.fn(), error: vi.fn() },
  });
});

describe("useMarketingOffers", () => {
  it("normaliza o erro do servidor por campo", () => {
    expect(
      marketingOfferProblem({
        data: {
          detail: "Revise.",
          field_errors: { coupon_code: ["Código repetido."] },
        },
      }),
    ).toEqual({
      detail: "Revise.",
      fieldErrors: { coupon_code: ["Código repetido."] },
    });
  });

  it("bloqueia o segundo submit enquanto o primeiro está em voo", async () => {
    let finish!: (value: unknown) => void;
    const request = new Promise((resolve) => {
      finish = resolve;
    });
    const refresh = vi.fn();
    const fetch = vi.fn(() => request);
    Object.assign(globalThis, {
      useFetch: vi.fn(() => ({
        data: ref({ offers: [], options: undefined }),
        refresh,
        pending: ref(false),
        error: ref(null),
      })),
      $fetch: fetch,
    });
    const offers = useMarketingOffers();
    const payload = { kind: "offer" };

    const first = offers.create(payload);
    const second = await offers.create(payload);

    expect(second).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
    finish({ ok: true, offer: { ref: "uma" } });
    await first;
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
