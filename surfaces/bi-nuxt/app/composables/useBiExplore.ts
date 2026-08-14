// Explorador (F8): métrica × até 2 dimensões, janela compartilhada. A
// gramática viaja NO relatório (`metrics`) — a UI monta os selects a partir
// dela, nunca de uma lista paralela. Erro de gramática vira mensagem, não
// tela quebrada.
import type { BIExploreReport } from "~/generated/biContract";

export interface ExploreConfig {
  metric: string;
  by: string;
  by2: string;
}

export function useBiExplore() {
  const { range } = useBiWindow();
  const config = useState<ExploreConfig>("bi-explore", () => ({
    metric: "revenue",
    by: "time",
    by2: "",
  }));

  const { data, pending, error, refresh } = useFetch<{ bi: BIExploreReport }>(
    "/api/v1/backstage/bi/explore/",
    {
      key: "bi-explore",
      server: true,
      query: computed(() => ({ ...range.value, ...config.value })),
      onResponseError: operatorSessionOnError,
    },
  );

  const report = computed(() => data.value?.bi ?? null);
  const errorDetail = computed(() => {
    const raw = error.value ? httpError(error.value).data : null;
    return (raw as { detail?: string } | null)?.detail ?? "";
  });

  function apply(next: Partial<ExploreConfig>) {
    const merged = { ...config.value, ...next };
    // Trocar a métrica pode invalidar as dimensões: volta para o chão seguro.
    const spec = report.value?.metrics.find((m) => m.key === merged.metric);
    if (spec) {
      if (!spec.dimensions.includes(merged.by)) merged.by = spec.dimensions[0] ?? "time";
      if (merged.by2 && (merged.by2 === merged.by || !spec.dimensions.includes(merged.by2))) {
        merged.by2 = "";
      }
    }
    config.value = merged;
  }

  return { config, report, pending, error, errorDetail, refresh, apply };
}
