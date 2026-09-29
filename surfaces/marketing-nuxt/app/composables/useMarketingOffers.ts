import type { MarketingOffer, MarketingOffersResponse } from "~/types/campaign";

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

  async function create(
    payload: Record<string, unknown>,
  ): Promise<MarketingOffer | null> {
    if (saving.value) return null;
    saving.value = true;
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
    refresh,
    create,
  };
}
