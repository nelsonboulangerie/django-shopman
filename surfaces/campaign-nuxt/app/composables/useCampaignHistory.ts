// Histórico — o que já saiu, com o resultado de cada plataforma.
//
// Sem poll: histórico é passado, não muda sozinho na tela. Quem quer o agora
// olha o painel.
import type { HistoryResponse } from "~/types/campaign";

export function useCampaignHistory() {
  const { data, refresh, pending, error } = useFetch<HistoryResponse>(
    "/api/v1/backstage/campaign/history/",
    { key: "campaign-history", server: true },
  );

  return {
    posts: computed(() => data.value?.posts ?? []),
    loading: pending,
    error,
    refresh,
  };
}
