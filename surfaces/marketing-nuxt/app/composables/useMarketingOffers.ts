import type { MarketingOffer, MarketingOffersResponse } from "~/types/campaign";

export interface MarketingOfferProblem {
  detail: string;
  fieldErrors: Record<string, string[]>;
}

export function marketingOfferProblem(error: unknown): MarketingOfferProblem {
  const failure = error as {
    data?: Record<string, unknown>;
    response?: { _data?: Record<string, unknown> };
  };
  const data = failure?.data || failure?.response?._data || {};
  const rawFields = data.field_errors;
  const fieldErrors: Record<string, string[]> = {};
  if (rawFields && typeof rawFields === "object") {
    for (const [field, messages] of Object.entries(rawFields)) {
      fieldErrors[field] = Array.isArray(messages)
        ? messages.map(String)
        : [String(messages)];
    }
  }
  return {
    detail:
      typeof data.detail === "string"
        ? data.detail
        : "Não foi possível salvar. Revise os campos destacados.",
    fieldErrors,
  };
}

export function useMarketingOffers() {
  const { data, refresh, pending, error } = useFetch<MarketingOffersResponse>(
    "/api/v1/backstage/marketing/offers/",
    {
      key: "marketing-offers",
      server: true,
      onResponseError: marketingSessionOnError,
    },
  );
  const saving = ref(false);
  const problem = ref<MarketingOfferProblem | null>(null);

  async function create(
    payload: Record<string, unknown>,
  ): Promise<MarketingOffer | null> {
    if (saving.value) return null;
    saving.value = true;
    problem.value = null;
    try {
      const response = await $fetch<{ ok: boolean; offer: MarketingOffer }>(
        "/api/v1/backstage/marketing/offers/",
        { method: "POST", body: payload },
      );
      await refresh();
      useSonner.success(
        payload.kind === "coupon" ? "Cupom criado." : "Oferta criada.",
      );
      return response.offer;
    } catch (err) {
      flagMarketingSessionError(err);
      problem.value = marketingOfferProblem(err);
      useSonner.error(
        httpErrorMessage(
          err,
          payload.kind === "coupon"
            ? "Não foi possível criar o cupom."
            : "Não foi possível criar a oferta.",
        ),
      );
      return null;
    } finally {
      saving.value = false;
    }
  }

  return {
    offers: computed(() => data.value?.offers ?? []),
    options: computed(() => data.value?.options),
    loading: pending,
    error,
    saving,
    problem,
    refresh,
    create,
    clearProblem: () => {
      problem.value = null;
    },
  };
}
