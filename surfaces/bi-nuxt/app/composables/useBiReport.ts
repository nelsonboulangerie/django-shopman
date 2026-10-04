// Um fetch por relatório de B.I. (production/sales/cash/customers), com a
// janela compartilhada na query. Leitura calma: sem poll — o gestor recarrega
// ou troca a janela; análise não é telemetria de turno (ADR-016 não se aplica
// a tendência). `extra` leva os recortes próprios da tela (o canal e a base de
// comparação das Vendas), que moram na URL como a janela.
import type { Ref } from "vue";

export function useBiReport<T>(
  kind: "production" | "sales" | "cash" | "customers",
  extra?: Ref<Record<string, string>>,
) {
  const { range } = useBiWindow();

  const { data, pending, error, refresh } = useFetch<{ bi: T }>(
    `/api/v1/backstage/bi/${kind}/`,
    {
      key: `bi-${kind}`,
      server: true,
      query: computed(() => ({ ...range.value, ...(extra?.value ?? {}) })),
      onResponseError: operatorSessionOnError,
    },
  );

  const report = computed(() => data.value?.bi ?? null);

  return { report, pending, error, refresh, data };
}
