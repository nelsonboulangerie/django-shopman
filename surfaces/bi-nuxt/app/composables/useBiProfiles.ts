// Perfis de consumo (BI-CONSUMPTION-PROFILES): A/B/C do balcão, presumidos
// pela cesta, em três leituras. Janela compartilhada + dois recortes próprios
// (dia da semana, faixa por ocasião) que viajam na query; o servidor normaliza
// valor fora do vocabulário para "todos" — aqui é UX, o contrato é dele.
import type { BIConsumptionProfilesReport } from "~/generated/biContract";

export interface ProfilesFilters {
  weekday: string; // "" = todos; "0" = segunda
  hour_band: string; // "" = todas
}

export function useBiProfiles() {
  const { range } = useBiWindow();
  const filters = useState<ProfilesFilters>("bi-profiles", () => ({
    weekday: "",
    hour_band: "",
  }));

  const { data, pending, error, refresh } = useFetch<{ bi: BIConsumptionProfilesReport }>(
    "/api/v1/backstage/bi/consumption-profiles/",
    {
      key: "bi-consumption-profiles",
      server: true,
      query: computed(() => ({ ...range.value, ...filters.value })),
      onResponseError: operatorSessionOnError,
    },
  );

  const report = computed(() => data.value?.bi ?? null);

  function apply(next: Partial<ProfilesFilters>) {
    filters.value = { ...filters.value, ...next };
  }

  return { filters, report, pending, error, refresh, apply };
}
