// Um fetch por relatório de B.I. (production/sales/cash/customers), com a
// janela compartilhada na query. Leitura calma: sem poll — o gestor recarrega
// ou troca a janela; análise não é telemetria de turno (ADR-016 não se aplica
// a tendência).
export function useBiReport<T>(kind: "production" | "sales" | "cash" | "customers") {
  const { range } = useBiWindow();

  const { data, pending, error, refresh } = useFetch<{ bi: T }>(
    `/api/v1/backstage/bi/${kind}/`,
    {
      key: `bi-${kind}`,
      server: true,
      query: range,
      onResponseError: operatorSessionOnError,
    },
  );

  const report = computed(() => data.value?.bi ?? null);

  return { report, pending, error, refresh };
}
